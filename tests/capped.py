"""P142: a redraw that the status line wrapper cut at its cap keeps no segment (P52), and the next redraw runs Pit
Board again. A test that needs Pit Board's part after a redraw makes that redraw again, at most TRIES times, and only
while it was cut; a try beyond the first is said as a warning that names the test, the try and each try's time, so a
run's summary shows a slow leg and the sightings can be counted. The cap and the wrapper are never changed for a test.

Where the programs a redraw starts are counted, the test's own helper asks more (tests/test_g10_p54_no_python.py,
kept()). Here, where they are not, the time is the guard: a redraw on the quiet road never takes the cap's time, and
a call that ended under the cap is the tree's answer, never tried again."""
import os
import time
import warnings

from pitboard import setup as S

TRIES = 5


def said(what, times):
    """The warning for a try beyond the first: `what` is what the last try did ('segment kept', 'part printed')."""
    test = os.environ.get("PYTEST_CURRENT_TEST", "?").rsplit(" (", 1)[0]
    warnings.warn(f"{test}: Pit Board's {what} on try {len(times)} of {TRIES}; the wrapper cut each try before it at "
                  f"its cap; times {', '.join(f'{x:.2f} s' for x in times)}")


def again_while_cut(call, has_part):
    """`call()` makes one whole redraw and returns what it printed. It is made again only while that lacks Pit Board's
    part (`has_part` says) AND the call took the cap's time. Returns the last thing printed: the test's own
    assertions decide on it. After TRIES calls that were all cut, it fails with each try's time."""
    times = []
    for _ in range(TRIES):
        t = time.monotonic()
        out = call()
        times.append(time.monotonic() - t)
        if has_part(out):
            if len(times) > 1:
                said("part printed", times)
            return out
        if times[-1] < S.STATUS_CAP_SECONDS:
            return out                                   # not cut at the cap: the tree's own answer
    raise AssertionError(f"Pit Board's part was never printed: {len(times)} tries, each cut at the cap; times "
                         + ", ".join(f"{x:.2f} s" for x in times))
