"""The suite's guard (P51, the family's rule 17, THE GUARD HAS FIVE PARTS). A test never uses the home or the tools
of the account running the suite.

1. Before anything imports the tool, the whole run gets its own temporary home (and its own tmux folder), loses this
   account's lines to its session (XDG_RUNTIME_DIR, DBUS_SESSION_BUS_ADDRESS, TMUX, TMUX_PANE) and Pit Board's own
   settings from the shell that started it; git finds no global or system config there. Every child inherits that.
2. What answers for the account and not for its home (claude, tmux, crontab, systemctl, loginctl, launchctl)
   resolves first to a stand-in that exits loudly; a test brings its own.
3. A hook in the test process counts: an open, listing or change in the real home outside this checkout and
   Python's own libraries; a child handed the real home, or none; one of those programs found outside a temporary
   folder.
4. The count fails the test in its own result, also when the test swallowed the error.
5. A gate test (tests/test_g20_ci.py) plants a test for each kind, sees each one caught, and sees them pass with the
   guard taken out.
The guard has no switch: nothing here reads a setting that takes it out or sends the run to the real home. The gate
test takes the hook out only in its own planted copy of this file, and a test holds that this file reads no such
setting.
Not seen by the hook: a read that only stats a path (no audit event), and what a child does by itself (parts 1 and 2
are for those).
"""
import os
import shutil
import site
import sys
import sysconfig
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    import pwd
    REAL_HOME = os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)
except (ImportError, KeyError):
    REAL_HOME = os.path.realpath(os.path.expanduser("~"))
os.environ.setdefault("PYTHONUSERBASE", site.getuserbase())   # the runner's own pytest stays importable in a child
_SESSION_TMP = os.path.realpath(tempfile.mkdtemp(prefix="pitboard-tests-"))
os.environ.update(HOME=os.path.join(_SESSION_TMP, "home"), TMUX_TMPDIR=os.path.join(_SESSION_TMP, "tmux"),
                  GIT_CONFIG_NOSYSTEM="1")
for _k in ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "TMUX", "TMUX_PANE", "PITBOARD_HOME", "PITBOARD_LANE",
           "PITBOARD_MACHINE", "PITBOARD_TZ", "PITBOARD_SELF_UPDATE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PLUGIN_ROOT",
           "CLAUDE_CONFIG_DIR", "GIT_CONFIG_GLOBAL"):
    os.environ.pop(_k, None)
os.makedirs(os.environ["HOME"])
os.makedirs(os.environ["TMUX_TMPDIR"])
_SYSTEM = ("claude", "tmux", "crontab", "systemctl", "loginctl", "launchctl")
_STUBS = os.path.join(_SESSION_TMP, "stubs")
os.makedirs(_STUBS)
for _n in _SYSTEM:
    with open(os.path.join(_STUBS, _n), "w") as _f:
        _f.write(f'#!/bin/sh\necho "rule 17 stub: {_n} $* (a test brings its own {_n})" >&2\nexit 97\n')
    os.chmod(os.path.join(_STUBS, _n), 0o755)
os.environ["PATH"] = _STUBS + os.pathsep + os.environ.get("PATH", "")
def _libraries():
    out = [sys.prefix, sys.base_prefix, sys.exec_prefix, getattr(sys, "base_exec_prefix", sys.exec_prefix),
           *sysconfig.get_paths().values()]
    try:
        out.append(site.getusersitepackages())
    except AttributeError:
        pass
    return out + [x for x in sys.path if x and ("site-packages" in x or "dist-packages" in x)]


# Left out of the watch: this checkout, the run's own folder and Python's own libraries. A place left out is never the
# home itself or a folder above it, nor one that holds the home's .pitboard, .claude, .config or Library/LaunchAgents.
_KEPT = [os.path.join(REAL_HOME, x) for x in (".pitboard", ".claude", ".config", os.path.join("Library", "LaunchAgents"))]
_ALLOWED = sorted({r for r in map(os.path.realpath, [ROOT, _SESSION_TMP] + [p for p in _libraries() if p])
                   if r != REAL_HOME and not REAL_HOME.startswith(r + os.sep)
                   and not any(k == r or k.startswith(r + os.sep) for k in _KEPT)})
_TEMP = sorted({os.path.realpath(tempfile.gettempdir()), "/tmp", os.path.realpath("/tmp"), _SESSION_TMP})
_seen = {"test": None, "hits": []}


def _under(p, roots):
    try:
        p = os.path.realpath(os.fsdecode(p))
    except (TypeError, ValueError):
        return False
    return any(p == r or p.startswith(r + os.sep) for r in roots)


def _audit(event, args):
    if not _seen["test"]:
        return
    if event in ("open", "os.listdir", "os.scandir", "glob.glob", "os.chmod", "os.chown", "os.remove", "os.mkdir",
                 "os.rmdir", "shutil.rmtree", "os.utime", "os.truncate", "os.rename", "os.replace", "os.symlink",
                 "os.link", "shutil.copyfile", "shutil.copytree", "shutil.move", "os.unlink"):
        two = event in ("os.rename", "os.replace", "os.symlink", "os.link", "shutil.copyfile", "shutil.copytree",
                        "shutil.move")
        for a in (args[:2] if two else args[:1]):          # a rename or copy INTO the home counts as much as out of it
            if isinstance(a, (str, bytes, os.PathLike)) and _under(a, [REAL_HOME]) and not _under(a, _ALLOWED):
                _seen["hits"].append(f"{event} {os.fsdecode(a)}")
    elif event == "subprocess.Popen":
        _exe, argv, _cwd, env = args
        env = os.environ if env is None else {os.fsdecode(k): os.fsdecode(v) for k, v in env.items()}
        argv = [os.fsdecode(a) for a in (argv or [])] if not isinstance(argv, (str, bytes)) else [os.fsdecode(argv)]
        home = env.get("HOME")
        if not home or os.path.realpath(home) == REAL_HOME:
            _seen["hits"].append(f"a child with {'no HOME' if not home else 'the real HOME'}: {' '.join(argv)[:100]}")
        if argv and os.path.basename(argv[0]) in _SYSTEM:
            found = argv[0] if os.sep in argv[0] else shutil.which(argv[0], path=env.get("PATH"))
            if found and not _under(found, _TEMP):
                _seen["hits"].append(f"this machine's own {os.path.basename(argv[0])}: {' '.join(argv)[:100]}")


sys.addaudithook(_audit)


def _guard_says(hits):
    hits = list(dict.fromkeys(hits))
    return ("rule 17: this test reached the home or the tools of the account running the suite: "
            + "; ".join(hits[:5]) + (f"; and {len(hits) - 5} more" if len(hits) > 5 else ""))


@pytest.fixture(autouse=True)
def _own_home_only(request):
    _seen.update(test=request.node.nodeid, hits=[])
    yield
    hits, _seen["test"] = _seen["hits"], None
    if hits:
        pytest.fail(_guard_says(hits), pytrace=False)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if call.when == "call" and _seen["hits"] and rep.passed:
        rep.outcome, rep.longrepr = "failed", _guard_says(_seen["hits"])
        _seen["hits"] = []                              # said once, in the test's own result


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_SESSION_TMP, ignore_errors=True)


if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
