# Focus Timer

[![CI](https://github.com/darkspaz-v1/focus-timer/actions/workflows/ci.yml/badge.svg)](https://github.com/darkspaz-v1/focus-timer/actions/workflows/ci.yml)

A Pomodoro timer that nudges instead of enforcing.

## How it works

- Always-on-top widget. Configurable work / short break / long break, defaulting to 25 / 5 / 15 minutes.
- During a focus block, if the foreground window matches a configured distraction pattern, the widget
  **flashes its border and raises itself**. That is all it does.

## The design decision worth stating

It deliberately **does not edit the hosts file, kill processes, or block anything**. Hard blockers
create an adversarial relationship with your own tooling: you end up disabling the blocker, and then
it protects nothing. A nudge that is easy to ignore gets left switched on, which makes it the option
that actually runs.

The work-duration control was revised twice after real use — config-file only, then +/- buttons, then
a typeable minutes field, which is what it has now. The first two were too slow to change mid-session,
so the timer got closed instead of adjusted.

**Stack:** Python, Tkinter, `pystray`, Pillow.

## Part of a suite

One of seven small Windows tray utilities built as separate, self-contained apps: each has its own
folder, its own virtualenv and its own `run.bat`, with no shared runtime. They are deliberately not a
framework — the only thing they share is a set of conventions.

| Convention | Why |
|---|---|
| Single-instance guard via a `.singleton.lock` file | An earlier `.instance.lock` design could get stuck after a force-kill and leave the app permanently unlaunchable |
| Relaunch brings the existing window forward | Previously a second launch silently did nothing, which was indistinguishable from the app being broken |
| Config lives in `config.json`, read at startup | Edit it, then fully exit the tray icon and relaunch — a running process never re-reads it |
| Tray icon generated in code (`icon.py`) | No binary asset to keep in sync |

## Install and run

```
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
run.bat
```

`run.bat` launches the app from `venv\` with no console window. Windows only - these use Win32 APIs and a
system tray.

## Tests

```
venv\Scripts\python -m pip install -r requirements-dev.txt
venv\Scripts\python -m pytest
venv\Scripts\python -m ruff check .
```

The tests cover the pure logic - the work/break/pause state machine, long-break cycling, and the distraction-nudge rule - and never open the widget or tray icon.

## Troubleshooting: log file location

Warnings and errors are written to `logs/focus-timer.log` in the app folder (rotating, gitignored). A crash on
startup also appends a traceback to `app_error.log` next to it.

## License

MIT — see [LICENSE](LICENSE).
