import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# P51 (the family's rule 17, A TEST THAT PASSES HERE AND FAILS ON A STOCK RUNNER LEANS ON THIS MACHINE): every test
# that loads or starts the tool gives it the test's own temporary home. This guard fails a test that, in this process,
# opens, lists, writes or removes anything under the real home's Pit Board home, settings file or plugin registry (the
# home of the account running the suite, read once here, before any test changes HOME); that starts a child whose
# HOME is that real home, or that has no HOME (it would find the real one); or that starts the real `claude` program
# (a temporary HOME does not cover a program of the user's own session). Not seen: a read by stat alone (no audit
# event), and what a child does inside itself beyond the HOME it was given.
REAL_HOME = os.path.expanduser("~")
WATCH = [os.path.join(h, *rel) for h in sorted({os.path.abspath(REAL_HOME), os.path.realpath(REAL_HOME)})   # as typed,
         for rel in ((".pitboard",), (".claude", "settings.json"), (".claude", "plugins"))]          # and resolved
TOUCHED = []
_CLAUDE = shutil.which("claude")
REAL_CLAUDE = os.path.realpath(_CLAUDE) if _CLAUDE else None


def _home_of(path):
    return os.path.realpath(path) in {os.path.abspath(REAL_HOME), os.path.realpath(REAL_HOME)}


def _child(executable, args, env):
    environ = os.environ if env is None else {os.fsdecode(k): os.fsdecode(v) for k, v in env.items()}
    argv = list(args) if isinstance(args, (list, tuple)) else [args]
    if [os.fsdecode(a) for a in argv[1:3]] == ["-m", "pytest"]:   # this suite run again (the promise gate): it loads
        return                                                     # this guard itself, against the same real home
    home = environ.get("HOME")
    if not home:
        TOUCHED.append("a child with no HOME (it finds the real one)")
    elif _home_of(home):
        TOUCHED.append(f"a child whose HOME is the real home: {home}")
    prog = os.fsdecode(executable if executable is not None else (argv[0] if argv else ""))
    found = prog if os.sep in prog else shutil.which(prog, path=environ.get("PATH"))
    if REAL_CLAUDE and found and os.path.realpath(found) == REAL_CLAUDE:
        TOUCHED.append(f"the real claude program: {found}")
_EVENTS = {"open", "os.listdir", "os.scandir", "os.mkdir", "os.remove", "os.rename", "os.replace", "os.chmod",
           "os.rmdir", "shutil.rmtree", "os.unlink", "os.symlink", "os.utime", "shutil.copyfile", "shutil.move"}


def _hook(event, args):
    if event == "subprocess.Popen":
        try:
            _child(args[0], args[1], args[3])
        except Exception as e:  # noqa: BLE001                      # never break the test's own call
            TOUCHED.append(f"a child the guard could not read: {type(e).__name__}")
        return
    if event not in _EVENTS or not args or isinstance(args[0], int) or args[0] is None:
        return
    try:
        path = os.path.abspath(os.fsdecode(args[0]))
    except (TypeError, ValueError):
        return
    for w in WATCH:
        if path == w or path.startswith(w + os.sep):
            TOUCHED.append(f"{event} {path}")
            return


sys.addaudithook(_hook)


@pytest.fixture(autouse=True)
def never_the_real_home():
    TOUCHED.clear()
    yield
    if TOUCHED:
        seen = sorted(set(TOUCHED))
        TOUCHED.clear()
        pytest.fail("this test reached the real home of the account running the suite (give it its own HOME): "
                    + "; ".join(seen[:5]), pytrace=False)
