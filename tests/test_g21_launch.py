"""G21.4: the launcher picks the version folder; every step in the plan's order."""
import ast
import json
import os
import shutil
import subprocess
import sys

import pytest

from pitboard import launch as L

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCH = os.path.join(ROOT, "pitboard", "launch.py")


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A fake HOME with ~/.claude and $PITBOARD_HOME."""
    home = tmp_path / "home"
    claude = home / ".claude"
    pb = tmp_path / "pb"
    (claude / "plugins" / "cache").mkdir(parents=True)
    (pb / "update").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PITBOARD_HOME", str(pb))
    monkeypatch.delenv("PITBOARD_SELF_UPDATE", raising=False)

    class W:
        pass
    w = W()
    w.home, w.claude, w.pb, w.tmp = home, claude, pb, tmp_path
    w.installed = []

    def version(v, market="thewindstorm", orphaned=False, runnable=True):
        f = claude / "plugins" / "cache" / market / L.PLUGIN / v
        (f / "pitboard").mkdir(parents=True)
        (f / "pitboard" / "__init__.py").write_text("")
        if runnable:
            (f / "pitboard" / "cli.py").write_text(
                "import sys\ndef main():\n    print('ran %s', sys.argv[1:])\n    return 0\n" % v)
        if orphaned:
            (f / ".orphaned_at").write_text("1")
        return str(f)

    def install(path, v, scope="user", market="thewindstorm"):
        w.installed.append((f"{L.PLUGIN}@{market}", {"scope": scope, "installPath": path, "version": v}))
        plugins = {}
        for k, e in w.installed:
            plugins.setdefault(k, []).append(e)
        (claude / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": plugins}))

    def lines(name, *vs):
        (pb / "update" / name).write_text("".join(v + "\n" for v in vs))

    w.version, w.install, w.lines = version, install, lines
    return w


def pick(w, own=None):
    return L.choose(home=str(w.pb), claude_dir=str(w.claude), own_root=own)


def test_G21_4_step1_pin_wins_unless_bad_or_missing(world):
    a, b = world.version("0.1.0"), world.version("0.2.0")
    world.install(b, "0.2.0")
    world.lines("good-versions", "0.1.0", "0.2.0")
    world.lines("pin", "0.1.0")
    assert pick(world) == (a, 1)
    world.lines("bad-versions", "0.1.0")
    assert pick(world) == (b, 3)
    world.lines("pin", "9.9.9")
    assert pick(world) == (b, 3)


def test_G21_4_step2_self_update_off_runs_the_install(world, monkeypatch):
    world.version("0.3.0")
    old = world.version("0.1.0")
    world.install(old, "0.1.0")
    world.lines("good-versions", "0.3.0")
    world.lines("bad-versions", "0.1.0")
    (world.pb / "config.json").write_text(json.dumps({"self_update": False}))
    assert pick(world) == (old, 2)          # G21.12: whatever its version
    monkeypatch.setenv("PITBOARD_SELF_UPDATE", "1")
    assert pick(world)[1] == 4
    monkeypatch.setenv("PITBOARD_SELF_UPDATE", "0")
    assert pick(world) == (old, 2)


def test_G21_4_step3_install_if_good_user_scope_first(world):
    proj, user = world.version("0.2.0", market="other"), world.version("0.2.1")
    world.install(proj, "0.2.0", scope="project", market="other")
    world.install(user, "0.2.1")
    world.lines("good-versions", "0.2.0", "0.2.1")
    assert pick(world) == (user, 3)


def test_G21_4_step4_highest_good_cached_not_orphaned(world):
    world.version("0.9.0")                                   # not good yet
    world.version("0.4.0", orphaned=True)
    world.version("0.3.0", runnable=False)
    two, ten = world.version("0.2.0"), world.version("0.10.0")
    world.lines("good-versions", "0.2.0", "0.3.0", "0.4.0", "0.10.0")
    assert pick(world) == (ten, 4)                           # 0.10.0 > 0.2.0 (numbers, not text)
    world.lines("bad-versions", "0.10.0")
    assert pick(world) == (two, 4)


def test_G21_4_step5_own_folder_before_unchecked_install(world):
    inst = world.version("0.2.0")
    world.install(inst, "0.2.0")
    own = world.version("0.1.0", market="dev")
    assert pick(world, own=own) == (own, 5)
    assert pick(world, own=str(world.pb)) == (inst, 6)       # the stable copy has no cli.py beside it


def test_G21_4_step6_and_7(world):
    assert pick(world) == (None, 7)
    inst = world.version("0.2.0")
    world.install(inst, "0.2.0")
    assert pick(world) == (inst, 6)
    world.lines("bad-versions", "0.2.0")
    assert pick(world) == (None, 7)


def test_G21_4_broken_files_do_not_crash(world):
    (world.claude / "plugins" / "installed_plugins.json").write_text("{not json")
    (world.pb / "config.json").write_text("[1, 2]")
    assert pick(world) == (None, 7)


def _run(w, script, *args):
    env = dict(os.environ, HOME=str(w.home), PITBOARD_HOME=str(w.pb))
    return subprocess.run([sys.executable, "-I", script, *args], capture_output=True, text=True, env=env,
                          timeout=60)


def test_G21_4_stable_copy_runs_the_newest_good_version(world):
    """The stable copy is launch.py alone; it calls the chosen version's cli.main() with the arguments."""
    stable = world.pb / "pitboard"
    stable.mkdir()
    shutil.copy(LAUNCH, stable / "launch.py")
    world.version("0.1.0")
    world.version("0.2.0")
    world.lines("good-versions", "0.1.0", "0.2.0")
    r = _run(world, str(stable / "launch.py"), "board", "--plain")
    assert r.returncode == 0 and r.stdout.strip() == "ran 0.2.0 ['board', '--plain']", r.stderr


def test_G21_4_step7_message_and_hooks_exit_0(world):
    stable = world.pb / "pitboard"
    stable.mkdir()
    shutil.copy(LAUNCH, stable / "launch.py")
    r = _run(world, str(stable / "launch.py"), "board")
    assert r.returncode == 1 and r.stderr == "pitboard: no installed version found\n" and r.stdout == ""
    r = _run(world, str(stable / "launch.py"), "hook", "stop")
    assert r.returncode == 0 and r.stderr == "" and r.stdout == ""


def test_G21_4_launcher_stays_tiny_and_imports_no_pit_board_code():
    with open(LAUNCH, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    top = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            top |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            top.add(node.module.split(".")[0])
    assert top <= {"json", "os", "re", "sys", "pitboard"}
    # the only Pit Board import is the chosen version's cli, inside main()
    assert src.count("from pitboard import cli") == 1 and "from ." not in src
    assert len(src.splitlines()) < 200
