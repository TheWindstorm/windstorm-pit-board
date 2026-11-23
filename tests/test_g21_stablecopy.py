"""G21.4 / G7.1 step 5 (plan 1.16): the session-start hook refreshes the stable launcher copy."""
import json
import os
import shutil
import subprocess
import sys

import pytest

from pitboard import __version__, stablecopy as SC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = __version__
OLD_LAUNCH = b"# a launcher from an earlier release\n" + open(os.path.join(ROOT, "pitboard", "launch.py"), "rb").read()
OLD_BIN = open(os.path.join(ROOT, "bin", "pitboard"), "rb").read()


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A fake HOME whose plugin cache holds this code as an installed version, and a Pit Board home
    set up by an earlier release (its launcher differs, no copied-from)."""
    home, pb = tmp_path / "home", tmp_path / "pb"
    claude = home / ".claude"
    ver = claude / "plugins" / "cache" / "mk" / "windstorm-pit-board" / V
    shutil.copytree(os.path.join(ROOT, "pitboard"), ver / "pitboard", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(os.path.join(ROOT, "bin"), ver / "bin")
    (claude / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
        "windstorm-pit-board@mk": [{"scope": "user", "installPath": str(ver), "version": V}]}}))
    (pb / "bin").mkdir(parents=True)
    (pb / "pitboard").mkdir()
    (pb / "update").mkdir()
    (pb / "bin" / "pitboard").write_bytes(OLD_BIN)
    os.chmod(pb / "bin" / "pitboard", 0o755)
    (pb / "pitboard" / "launch.py").write_bytes(OLD_LAUNCH)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PITBOARD_HOME", str(pb))
    monkeypatch.delenv("PITBOARD_SELF_UPDATE", raising=False)
    return home, pb, ver


def go(w, cfg=None, root=None):
    home, pb, ver = w
    return SC.refresh(str(pb), cfg or {"self_update": True}, root=str(root or ver), claude_dir=str(home / ".claude"))


def copy_of(pb):
    return (pb / "bin" / "pitboard").read_bytes(), (pb / "pitboard" / "launch.py").read_bytes()


def new_of(ver):
    return (ver / "bin" / "pitboard").read_bytes(), (ver / "pitboard" / "launch.py").read_bytes()


def leftovers(pb):
    return [n for d in (pb, pb / "bin", pb / "pitboard") for n in os.listdir(d)
            if n.startswith(".refresh-") or n.endswith(".tmp")]


def test_G21_4_refresh_replaces_an_older_copy_after_its_check(world):
    home, pb, ver = world
    assert go(world) == f"stable launcher before-0.1.2 -> {V}, backup kept"
    assert copy_of(pb) == new_of(ver) and (pb / "pitboard" / "copied-from").read_text() == V + "\n"
    assert (pb / "pitboard" / "launch.py.prev").read_bytes() == OLD_LAUNCH     # one backup of what it replaced
    assert not (pb / "bin" / "pitboard.prev").exists()                          # the same file is not backed up
    assert os.access(pb / "bin" / "pitboard", os.X_OK) and leftovers(pb) == []
    assert go(world) is None                                                    # up to date: nothing more


def test_G21_4_refresh_never_writes_older_over_newer(world):
    home, pb, ver = world
    (pb / "pitboard" / "copied-from").write_text("9.9.9\n")
    assert go(world) is None and copy_of(pb) == (OLD_BIN, OLD_LAUNCH)


def test_G21_4_refresh_mends_a_torn_copy(world):
    home, pb, ver = world
    (pb / "pitboard" / "copied-from").write_text(V + "\n")                     # marker says ours, files do not
    assert go(world) == f"stable launcher {V} -> {V}, backup kept" and copy_of(pb) == new_of(ver)


def test_G21_4_refresh_only_from_a_good_installed_version_with_self_update_on(world):
    home, pb, ver = world
    assert go(world, cfg={"self_update": False}) is None
    assert go(world, root=ROOT) is None                                         # a checkout, not the cache
    (pb / "update" / "bad-versions").write_text(V + "\n")
    assert go(world) is None
    assert copy_of(pb) == (OLD_BIN, OLD_LAUNCH) and not (pb / "pitboard" / "copied-from").exists()


def test_G21_4_refresh_never_makes_a_copy(world):
    home, pb, ver = world
    shutil.rmtree(pb / "pitboard")
    assert go(world) is None and not (pb / "pitboard").exists()


def test_G21_4_same_files_get_the_marker_only(world):
    home, pb, ver = world
    for rel in ("launch.py", "leave.py"):
        (pb / "pitboard" / rel).write_bytes((ver / "pitboard" / rel).read_bytes())
    assert go(world) is None and (pb / "pitboard" / "copied-from").read_text() == V + "\n"
    assert not (pb / "pitboard" / "launch.py.prev").exists()


@pytest.mark.parametrize("broken, why", [
    (b"raise SystemExit(3)\n", "answered exit 3"),
    (b"print('not a version line')\n", "answered exit 0"),
    (b"import time\ntime.sleep(30)\n", "did not answer in 1 s"),
])
def test_G21_4_a_broken_launcher_never_replaces_a_working_one(world, monkeypatch, broken, why):
    home, pb, ver = world
    monkeypatch.setattr(SC, "CHECK_SECONDS", 1)
    (ver / "pitboard" / "launch.py").write_bytes(broken)
    assert go(world) == f"stable launcher: this hook left the copy as it was (it read before-0.1.2 when it started): the {V} launcher {why}"
    assert copy_of(pb) == (OLD_BIN, OLD_LAUNCH) and leftovers(pb) == []
    assert not (pb / "pitboard" / "copied-from").exists() and not (pb / "pitboard" / "launch.py.prev").exists()


def test_G21_4_many_hooks_at_once_leave_one_whole_copy(world):
    """Twelve real session-start hooks of one home at the same moment, as after a reboot."""
    home, pb, ver = world
    env = dict(os.environ, HOME=str(home), PITBOARD_HOME=str(pb))
    env.pop("CLAUDE_ENV_FILE", None)
    procs = [subprocess.Popen([str(ver / "bin" / "pitboard"), "hook", "session-start"], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env) for _ in range(12)]
    outs = [p.communicate(json.dumps({"session_id": f"s{i}", "source": "resume", "cwd": str(home / f"lane{i}")}).encode(),
                          timeout=120) for i, p in enumerate(procs)]
    assert [p.returncode for p in procs] == [0] * 12 and all(e == b"" for _, e in outs)
    assert all(json.loads(o)["hookSpecificOutput"]["hookEventName"] == "SessionStart" for o, _ in outs)
    assert copy_of(pb) == new_of(ver) and (pb / "pitboard" / "copied-from").read_text() == V + "\n"
    assert (pb / "pitboard" / "launch.py.prev").read_bytes() == OLD_LAUNCH and leftovers(pb) == []
    log = (pb / "logs" / "pitboard.log").read_text()
    assert log.count(f"stable launcher before-0.1.2 -> {V}, backup kept") >= 1   # a hook slowed past its check keeps the copy
    r = subprocess.run([str(pb / "bin" / "pitboard"), "version"], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0 and r.stdout.startswith(f"{V} (installed {V}")
