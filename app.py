import json
import msvcrt
import queue
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path

import pystray
from PIL import ImageTk
from winotify import Notification, audio

from foreground import get_foreground_info, is_distracting
from icon import app_icon
from timer import FOCUS, IDLE, LONG_BREAK, PHASE_LABELS, SHORT_BREAK, PomodoroTimer, nudge_decision

APP_DIR = Path(__file__).parent
CONFIG_PATH = APP_DIR / "config.json"
LOCK_PATH = APP_DIR / ".singleton.lock"
SHOW_SIGNAL_PATH = APP_DIR / ".show_signal"
_lock_file = None

INK = "#12131C"
PANEL = "#1B1D2B"
PANEL_HOVER = "#242640"
HAIRLINE = "#2E3044"
TEXT = "#EDEEF7"
MUTED = "#8688A6"
ACCENT = "#E8603C"
BREAK_COLOR = "#3DDC97"
DANGER = "#F0576B"

DEFAULT_CONFIG = {
    "work_minutes": 25,
    "short_break_minutes": 5,
    "long_break_minutes": 15,
    "cycles_before_long_break": 4,
    "check_interval_seconds": 3,
    "distracting_processes": ["discord.exe"],
    "distracting_title_keywords": ["youtube", "reddit", "twitter", "x.com", "netflix"],
}


def _acquire_single_instance_lock():
    """Best-effort single-instance guard via an exclusive OS file lock (stdlib
    msvcrt, Windows-only, no extra dependency). Before exiting on a blocked
    second launch, drops a signal file so the already-running instance shows
    itself - otherwise launching an already-running app (e.g. from the Launcher)
    silently does nothing, which is indistinguishable from being broken."""
    global _lock_file
    f = open(LOCK_PATH, "a+b")
    if f.tell() == 0:
        f.write(b"0")
        f.flush()
    f.seek(0)
    try:
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        f.close()
        try:
            SHOW_SIGNAL_PATH.touch()
        except OSError:
            pass
        return False
    _lock_file = f
    return True


def load_config():
    config = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    except FileNotFoundError:
        pass
    return config


def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def _pick_mono_font():
    families = set(tkfont.families())
    for name in ("Cascadia Mono", "Cascadia Code", "Consolas"):
        if name in families:
            return name
    return "Consolas"


def notify(title, message):
    try:
        toast = Notification(app_id="Focus Timer", title=title, msg=message)
        toast.set_audio(audio.Default, loop=False)
        toast.show()
    except Exception:
        pass


PHASE_COLORS = {
    IDLE: MUTED,
    FOCUS: ACCENT,
    SHORT_BREAK: BREAK_COLOR,
    LONG_BREAK: BREAK_COLOR,
}


class FocusTimerApp:
    def __init__(self):
        self.config = load_config()
        self.timer = PomodoroTimer(self.config)
        self._was_distracting = False
        self._flash_job = None

        self.root = tk.Tk()
        self.root.title("Focus Timer")
        self.root.configure(bg=INK)
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        self._mono = _pick_mono_font()
        self._icon_photo = ImageTk.PhotoImage(app_icon())
        self.root.iconphoto(True, self._icon_photo)

        w, h = 260, 300
        x = self.root.winfo_screenwidth() - w - 20
        self.root.geometry(f"{w}x{h}+{x}+40")
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

        self._stop = threading.Event()
        self.icon = None
        self._ui_queue = queue.Queue()
        self.root.after(50, self._drain_ui_queue)

        self._build_ui()
        self.root.after(1000, self._tick_loop)
        self.root.after(self.config["check_interval_seconds"] * 1000, self._check_loop)
        self._refresh_display()

    def _drain_ui_queue(self):
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                fn()
        except queue.Empty:
            pass
        if SHOW_SIGNAL_PATH.exists():
            try:
                SHOW_SIGNAL_PATH.unlink()
            except OSError:
                pass
            self.root.deiconify()
            self.root.lift()
        self.root.after(50, self._drain_ui_queue)

    def _post(self, fn):
        self._ui_queue.put(fn)

    def _build_ui(self):
        self._accent_bar = tk.Frame(self.root, bg=ACCENT, height=2)
        self._accent_bar.pack(fill="x")

        header = tk.Frame(self.root, bg=INK)
        header.pack(fill="x", padx=14, pady=(10, 4))
        tk.Label(header, text="FOCUS TIMER", bg=INK, fg=ACCENT, font=(self._mono, 10, "bold")).pack(side="left")

        self.phase_label = tk.Label(self.root, text="READY", bg=INK, fg=MUTED, font=(self._mono, 10, "bold"))
        self.phase_label.pack(pady=(10, 0))

        self.time_label = tk.Label(self.root, text="25:00", bg=INK, fg=ACCENT, font=(self._mono, 36, "bold"))
        self.time_label.pack(pady=(2, 2))

        duration_row = tk.Frame(self.root, bg=INK)
        duration_row.pack(pady=(0, 4))

        self.duration_entry = tk.Entry(
            duration_row,
            width=4,
            justify="center",
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            disabledbackground=INK,
            disabledforeground=MUTED,
            relief="flat",
            font=("Segoe UI", 11),
            highlightthickness=1,
            highlightbackground=HAIRLINE,
            highlightcolor=ACCENT,
        )
        self.duration_entry.pack(side="left", padx=(0, 6), ipady=2)
        self.duration_entry.bind("<Return>", self._commit_duration_entry)
        self.duration_entry.bind("<FocusOut>", self._commit_duration_entry)

        tk.Label(duration_row, text="min", bg=INK, fg=MUTED, font=("Segoe UI", 10)).pack(side="left")

        self.cycle_label = tk.Label(self.root, text="", bg=INK, fg=MUTED, font=(self._mono, 12))
        self.cycle_label.pack()

        self.distraction_label = tk.Label(self.root, text="", bg=INK, fg=DANGER, font=(self._mono, 8))
        self.distraction_label.pack(pady=(4, 0))

        btns = tk.Frame(self.root, bg=INK)
        btns.pack(pady=(14, 0))
        self.start_btn = self._make_button(btns, "start", self.toggle_pause, accent=ACCENT)
        self.start_btn.pack(side="left", padx=3)
        self._make_button(btns, "skip", self.skip).pack(side="left", padx=3)
        self._make_button(btns, "reset", self.reset).pack(side="left", padx=3)

    def _make_button(self, parent, text, command, accent=None):
        fg = accent or TEXT
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=PANEL,
            fg=fg,
            activebackground=PANEL_HOVER,
            activeforeground=fg,
            font=(self._mono, 9, "bold"),
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=HAIRLINE,
            highlightcolor=HAIRLINE,
        )
        btn.bind("<Enter>", lambda e: btn.config(bg=PANEL_HOVER))
        btn.bind("<Leave>", lambda e: btn.config(bg=PANEL))
        return btn

    def toggle_pause(self, icon=None, item=None):
        was_idle = self.timer.state == IDLE
        self.timer.toggle_pause()
        if was_idle:
            notify("Focus session started", f"{self.config['work_minutes']} minutes - go.")
        self._refresh_display()

    def _commit_duration_entry(self, event=None):
        if self.timer.state != IDLE:
            self._sync_duration_entry()
            return
        raw = self.duration_entry.get().strip()
        try:
            value = int(raw)
        except ValueError:
            self._sync_duration_entry()
            return
        value = max(5, min(180, value))
        if value != self.config["work_minutes"]:
            self.config["work_minutes"] = value
            save_config(self.config)
        self._sync_duration_entry()
        self._refresh_display()
        self.root.focus_set()

    def _sync_duration_entry(self):
        was_disabled = self.duration_entry.cget("state") == "disabled"
        if was_disabled:
            self.duration_entry.config(state="normal")
        self.duration_entry.delete(0, tk.END)
        self.duration_entry.insert(0, str(self.config["work_minutes"]))
        if was_disabled:
            self.duration_entry.config(state="disabled")

    def skip(self, icon=None, item=None):
        self.timer.skip()
        self._refresh_display()

    def reset(self, icon=None, item=None):
        self.timer.reset()
        self._refresh_display()

    def _tick_loop(self):
        if self._stop.is_set():
            return
        finished = self.timer.tick()
        if finished:
            self._on_phase_finished(finished)
        self._refresh_display()
        self.root.after(1000, self._tick_loop)

    def _on_phase_finished(self, finished_phase):
        if finished_phase == FOCUS:
            notify(
                "Focus block complete",
                f"{self.timer.distraction_count} distraction(s). Time for a break.",
            )
        else:
            notify("Break's over", "Back to focus when you're ready.")

    def _check_loop(self):
        if self._stop.is_set():
            return
        distracting = False
        if self.timer.state == FOCUS and not self.timer.paused:
            process_name, title = get_foreground_info()
            distracting = is_distracting(process_name, title, self.config)
        nudge, self._was_distracting = nudge_decision(
            self.timer.state, self.timer.paused, distracting, self._was_distracting
        )
        if nudge:
            self.timer.register_distraction()
            self._flash_border()
            # deiconify first - lift() on a withdrawn (tray-hidden) window is a
            # silent no-op, so without this the nudge would never actually be seen.
            self.root.deiconify()
            self.root.lift()
            self._refresh_display()
        self.root.after(self.config["check_interval_seconds"] * 1000, self._check_loop)

    def _flash_border(self):
        if self._flash_job is not None:
            self.root.after_cancel(self._flash_job)
        self._accent_bar.config(bg=DANGER)

        def revert():
            self._accent_bar.config(bg=PHASE_COLORS.get(self.timer.state, ACCENT))
            self._flash_job = None

        self._flash_job = self.root.after(1200, revert)

    def _refresh_display(self):
        state = self.timer.state
        self.phase_label.config(text=PHASE_LABELS[state], fg=PHASE_COLORS[state])
        # At idle, remaining_seconds is 0 (no phase has started yet) - preview the
        # configured work-session length instead of showing a confusing "00:00".
        display_seconds = self.timer.remaining_seconds if state != IDLE else self.config["work_minutes"] * 60
        self.time_label.config(text=PomodoroTimer.format_time(display_seconds), fg=PHASE_COLORS[state])
        if self._flash_job is None:
            self._accent_bar.config(bg=PHASE_COLORS[state])

        editable = state == IDLE
        self.duration_entry.config(state="normal" if editable else "disabled")
        if self.root.focus_get() is not self.duration_entry:
            self._sync_duration_entry()

        cycles_before_long_break = max(1, self.config.get("cycles_before_long_break", 4))
        position = self.timer.completed_focus_cycles % cycles_before_long_break
        dots = "".join("●" if i < position else "○" for i in range(cycles_before_long_break))
        self.cycle_label.config(text=dots)

        if state == FOCUS and self.timer.distraction_count > 0:
            plural = "s" if self.timer.distraction_count != 1 else ""
            self.distraction_label.config(text=f"{self.timer.distraction_count} distraction{plural} this session")
        else:
            self.distraction_label.config(text="")

        if state == IDLE:
            self.start_btn.config(text="start")
        elif self.timer.paused:
            self.start_btn.config(text="resume")
        else:
            self.start_btn.config(text="pause")

    def hide_window(self):
        self.root.withdraw()

    def show_window(self, icon=None, item=None):
        self._post(self.root.deiconify)

    def quit_app(self, icon=None, item=None):
        self._stop.set()
        if self.icon:
            self.icon.stop()
        self._post(self.root.destroy)

    def run(self):
        menu = pystray.Menu(
            pystray.MenuItem("Show Timer", self.show_window, default=True),
            pystray.MenuItem("Start/Pause", lambda icon, item: self._post(self.toggle_pause)),
            pystray.MenuItem("Skip", lambda icon, item: self._post(self.skip)),
            pystray.MenuItem("Reset", lambda icon, item: self._post(self.reset)),
            pystray.MenuItem("Quit", self.quit_app),
        )
        self.icon = pystray.Icon("focus-timer", app_icon(), "Focus Timer", menu)
        threading.Thread(target=self.icon.run, daemon=True).start()
        self.root.mainloop()


def main():
    if not _acquire_single_instance_lock():
        return
    app = FocusTimerApp()
    app.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        with open(APP_DIR / "app_error.log", "a", encoding="utf-8") as f:
            f.write(f"\n--- {time.ctime()} ---\n")
            f.write(traceback.format_exc())
        raise
