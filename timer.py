IDLE = "idle"
FOCUS = "focus"
SHORT_BREAK = "short_break"
LONG_BREAK = "long_break"

PHASE_LABELS = {
    IDLE: "READY",
    FOCUS: "FOCUS",
    SHORT_BREAK: "SHORT BREAK",
    LONG_BREAK: "LONG BREAK",
}


class PomodoroTimer:
    """Pure state machine - no UI/timing side effects. Call tick() once per second
    from whatever drives real time (a Tk `after` loop, in this app)."""

    def __init__(self, config):
        self.config = config
        self.state = IDLE
        self.remaining_seconds = 0
        self.paused = False
        self.completed_focus_cycles = 0
        self.distraction_count = 0

    def start(self):
        if self.state == IDLE:
            self._begin_phase(FOCUS)
        else:
            self.paused = False

    def pause(self):
        if self.state != IDLE:
            self.paused = True

    def toggle_pause(self):
        if self.state == IDLE:
            self.start()
        elif self.paused:
            self.paused = False
        else:
            self.paused = True

    def skip(self):
        if self.state != IDLE:
            return self._advance()
        return None

    def reset(self):
        self.state = IDLE
        self.remaining_seconds = 0
        self.paused = False
        self.completed_focus_cycles = 0
        self.distraction_count = 0

    def register_distraction(self):
        if self.state == FOCUS and not self.paused:
            self.distraction_count += 1

    def tick(self):
        """Call once per second. Returns the phase that just finished, or None."""
        if self.state == IDLE or self.paused:
            return None
        self.remaining_seconds -= 1
        if self.remaining_seconds <= 0:
            return self._advance()
        return None

    def _begin_phase(self, phase):
        self.state = phase
        self.paused = False
        if phase == FOCUS:
            self.remaining_seconds = self.config["work_minutes"] * 60
            self.distraction_count = 0
        elif phase == SHORT_BREAK:
            self.remaining_seconds = self.config["short_break_minutes"] * 60
        elif phase == LONG_BREAK:
            self.remaining_seconds = self.config["long_break_minutes"] * 60

    def _advance(self):
        finished_phase = self.state
        if finished_phase == FOCUS:
            self.completed_focus_cycles += 1
            cycles_before_long_break = max(1, self.config.get("cycles_before_long_break", 4))
            if self.completed_focus_cycles % cycles_before_long_break == 0:
                self._begin_phase(LONG_BREAK)
            else:
                self._begin_phase(SHORT_BREAK)
        else:
            self._begin_phase(FOCUS)
        return finished_phase

    @staticmethod
    def format_time(seconds):
        seconds = max(0, int(seconds))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"


def nudge_decision(state, paused, distracting, was_distracting):
    """Distraction-nudge rule, kept pure so it can be tested. Returns
    (should_nudge, new_was_distracting). Only an unpaused FOCUS block can nudge, and
    only on the edge from not-distracting to distracting - staying on the same
    distracting window must not re-nudge every check. Outside a focus block the
    edge memory resets, so opening a distracting window during a break and then
    starting focus with it still open nudges once."""
    if state == FOCUS and not paused:
        return distracting and not was_distracting, distracting
    return False, False
