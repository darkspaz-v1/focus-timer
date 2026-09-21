import pytest

from timer import FOCUS, IDLE, LONG_BREAK, SHORT_BREAK, PomodoroTimer, nudge_decision

CFG = {
    "work_minutes": 2,
    "short_break_minutes": 1,
    "long_break_minutes": 3,
    "cycles_before_long_break": 4,
}


@pytest.fixture
def t():
    return PomodoroTimer(dict(CFG))


def run_out(timer):
    """Tick until the current phase finishes; returns the finished phase."""
    while True:
        finished = timer.tick()
        if finished:
            return finished


# --- state machine --------------------------------------------------------

def test_starts_idle_and_does_not_tick(t):
    assert t.state == IDLE
    assert t.tick() is None
    assert t.remaining_seconds == 0


def test_start_begins_focus_with_configured_duration(t):
    t.start()
    assert (t.state, t.remaining_seconds, t.paused) == (FOCUS, 120, False)


def test_tick_counts_down_and_finishing_focus_starts_short_break(t):
    t.start()
    for _ in range(119):
        assert t.tick() is None
    assert t.remaining_seconds == 1
    assert t.tick() == FOCUS
    assert (t.state, t.remaining_seconds) == (SHORT_BREAK, 60)
    assert t.completed_focus_cycles == 1


def test_break_finishing_returns_to_focus(t):
    t.start()
    run_out(t)
    assert run_out(t) == SHORT_BREAK
    assert (t.state, t.remaining_seconds) == (FOCUS, 120)


def test_long_break_after_every_nth_focus(t):
    t.start()
    phases = []
    for _ in range(8):  # four focus blocks and the four breaks they earn
        run_out(t)
        phases.append(t.state)
    assert phases == [SHORT_BREAK, FOCUS, SHORT_BREAK, FOCUS, SHORT_BREAK, FOCUS, LONG_BREAK, FOCUS]
    assert t.completed_focus_cycles == 4


def test_long_break_uses_its_own_duration(t):
    t.start()
    for _ in range(7):
        run_out(t)
    assert t.state == LONG_BREAK and t.remaining_seconds == 180


def test_cycles_before_long_break_is_clamped_to_at_least_one():
    timer = PomodoroTimer({**CFG, "cycles_before_long_break": 0})
    timer.start()
    run_out(timer)
    assert timer.state == LONG_BREAK  # every block earns a long break


# --- pause / resume -------------------------------------------------------

def test_pause_freezes_the_countdown_and_resume_continues(t):
    t.start()
    t.tick()
    t.pause()
    assert t.paused
    before = t.remaining_seconds
    for _ in range(10):
        assert t.tick() is None
    assert t.remaining_seconds == before
    t.toggle_pause()
    assert not t.paused
    t.tick()
    assert t.remaining_seconds == before - 1


def test_pause_while_idle_does_nothing_and_toggle_from_idle_starts(t):
    t.pause()
    assert not t.paused and t.state == IDLE
    t.toggle_pause()
    assert t.state == FOCUS


def test_start_while_paused_resumes(t):
    t.start()
    t.pause()
    t.start()
    assert not t.paused and t.state == FOCUS


def test_phase_change_clears_pause(t):
    t.start()
    t.pause()
    t.skip()
    assert t.state == SHORT_BREAK and not t.paused


# --- skip / reset ---------------------------------------------------------

def test_skip_returns_finished_phase_and_advances(t):
    t.start()
    assert t.skip() == FOCUS
    assert t.state == SHORT_BREAK
    assert t.skip() == SHORT_BREAK
    assert t.state == FOCUS


def test_skip_when_idle_is_a_noop(t):
    assert t.skip() is None
    assert t.state == IDLE


def test_reset_returns_everything_to_idle(t):
    t.start()
    run_out(t)
    t.register_distraction()
    t.reset()
    assert (t.state, t.remaining_seconds, t.paused) == (IDLE, 0, False)
    assert (t.completed_focus_cycles, t.distraction_count) == (0, 0)


# --- distractions counter -------------------------------------------------

def test_distractions_only_count_in_an_unpaused_focus_block(t):
    t.register_distraction()  # idle
    assert t.distraction_count == 0
    t.start()
    t.register_distraction()
    t.register_distraction()
    assert t.distraction_count == 2
    t.pause()
    t.register_distraction()
    assert t.distraction_count == 2
    t.toggle_pause()
    run_out(t)  # now in a short break
    t.register_distraction()
    assert t.distraction_count == 2


def test_distraction_count_resets_at_the_start_of_each_focus_block(t):
    t.start()
    t.register_distraction()
    run_out(t)  # break
    run_out(t)  # new focus
    assert t.state == FOCUS and t.distraction_count == 0


def test_format_time():
    assert PomodoroTimer.format_time(0) == "00:00"
    assert PomodoroTimer.format_time(65) == "01:05"
    assert PomodoroTimer.format_time(1500) == "25:00"
    assert PomodoroTimer.format_time(-5) == "00:00"
    assert PomodoroTimer.format_time(59.9) == "00:59"


# --- distraction-nudge decision ------------------------------------------

def test_nudge_fires_once_on_the_edge_into_a_distracting_window():
    assert nudge_decision(FOCUS, False, True, False) == (True, True)
    assert nudge_decision(FOCUS, False, True, True) == (False, True)  # still on it: no repeat


def test_nudge_rearms_after_leaving_the_distracting_window():
    assert nudge_decision(FOCUS, False, False, True) == (False, False)
    assert nudge_decision(FOCUS, False, True, False) == (True, True)


@pytest.mark.parametrize("state", [IDLE, SHORT_BREAK, LONG_BREAK])
def test_no_nudge_outside_focus_and_edge_memory_resets(state):
    assert nudge_decision(state, False, True, True) == (False, False)


def test_no_nudge_while_paused():
    assert nudge_decision(FOCUS, True, True, False) == (False, False)


def test_skipping_a_focus_block_still_counts_as_a_completed_cycle(t):
    # Documents current behaviour (skip = "finish now"): four skips reach the long break
    # without any real focus time. Flagged in the review notes; not changed.
    t.start()
    for _ in range(3):
        t.skip()  # focus -> short break
        t.skip()  # short break -> focus
    t.skip()
    assert t.state == LONG_BREAK
