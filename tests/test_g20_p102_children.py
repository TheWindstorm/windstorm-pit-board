"""P102 (G20): a test that starts child processes says in its failure which child, how it ended and what it last
printed. Before, such a test failed with `assert False`: the line named no child and no exit code."""
import os
import sys

import pytest

from children import run_children

OK = [sys.executable, "-c", "pass"]
SEVEN = [sys.executable, "-c", "import sys\nfor n in range(1, 9): sys.stderr.write('line %d\\n' % n)\nsys.exit(7)"]


def test_G20_P102_a_child_that_fails_or_does_not_end_is_named_with_how_it_ended_and_its_last_lines(tmp_path):
    """Three children at once: one ends well, one ends with 7 after eight error lines, one does not end in the time
    given. The answer names the second and the third, each with how it ended, and nothing of the third is left."""
    pidfile = tmp_path / "pid"
    slow = [sys.executable, "-c", "import os, sys, time\nopen(sys.argv[1], 'w').write(str(os.getpid()))\ntime.sleep(60)",
            str(pidfile)]
    assert run_children([OK, OK]) == []
    assert run_children([OK, SEVEN, slow], timeout=3) == [
        "child 2 of 3 ended with exit code 7; its last error lines: line 4 | line 5 | line 6 | line 7 | line 8",
        "child 3 of 3 did not end in 3 s and was stopped; its last error lines: none"]
    with pytest.raises(ProcessLookupError):                                  # the child that did not end is gone
        os.kill(int(pidfile.read_text()), 0)
