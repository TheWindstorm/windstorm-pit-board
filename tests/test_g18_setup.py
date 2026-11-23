"""G18.1: pitboard setup --minimal (config, stable launcher copy, status line wrapper)."""
import io
import json
import os
import shutil
import stat
import subprocess

import pytest

from pitboard import __version__, cli, setup as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def world(tmp_path, monkeypatch):
    home, pb = tmp_path / "home", tmp_path / "pb"
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PITBOARD_HOME", str(pb))
    monkeypatch.setenv("PITBOARD_MACHINE", "studio-1")
    for k in ("PITBOARD_LANE", "CLAUDE_CODE_SESSION_ID", "NO_COLOR"):
        monkeypatch.delenv(k, raising=False)
    return home, pb


def settings(home, obj=None):
    p = home / ".claude" / "settings.json"
    if obj is not None:
        p.write_text(json.dumps(obj))
    return json.loads(p.read_text()) if p.exists() else None


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    return cli.main(list(argv), stdout=out, stderr=err), out.getvalue(), err.getvalue()


def test_G18_1_plan_changes_nothing(world):
    home, pb = world
    settings(home, {"statusLine": {"type": "command", "command": "echo mine"}})
    before = (home / ".claude" / "settings.json").read_bytes()
    code, out, _ = run("setup", "--minimal")
    assert code == 0 and out.startswith("1. config file: ") and "Nothing changed. Run again with --apply" in out
    assert [ln.split(":")[0] for ln in out.splitlines() if ln[:1].isdigit()] == [
        "1. config file", "2. stable launcher copy", "3. stable launcher copy", "4. stable launcher copy",
        "5. stable launcher copy", "6. status line wrapper", "7. status line setting"]          # 4: leave.py (G18.3)
    assert not pb.exists() and (home / ".claude" / "settings.json").read_bytes() == before


def test_G18_1_full_setup_waits_for_0_2_0(world):
    code, _, err = run("setup")
    assert code == 2 and "--minimal" in err


def test_G18_1_apply_writes_everything_with_backups(world):
    home, pb = world
    settings(home, {"statusLine": {"type": "command", "command": "echo mine", "padding": 1}, "model": "x"})
    code, out, _ = run("setup", "--minimal", "--apply")
    assert code == 0 and out.endswith("Done: 7 change(s).\n")
    assert (pb / "pitboard" / "copied-from").read_text() == __version__ + "\n"     # plan 1.16
    cfg = json.loads((pb / "config.json").read_text())
    assert cfg["self_update"] is True and stat.S_IMODE(os.stat(pb / "config.json").st_mode) == 0o600
    assert (pb / "bin" / "pitboard").read_bytes() == open(os.path.join(ROOT, "bin", "pitboard"), "rb").read()
    assert os.access(pb / "bin" / "pitboard", os.X_OK)
    assert (pb / "pitboard" / "launch.py").read_bytes() == open(os.path.join(ROOT, "pitboard", "launch.py"), "rb").read()
    st = settings(home)
    assert st["statusLine"] == {"type": "command", "command": str(pb / "statusline.sh"), "padding": 1}
    assert st["model"] == "x"
    backups = [n for n in os.listdir(home / ".claude") if n.startswith("settings.json.bak-")]
    assert len(backups) == 1
    assert json.loads((home / ".claude" / backups[0]).read_text())["statusLine"]["command"] == "echo mine"
    assert S.original_from_wrapper(str(pb / "statusline.sh")) == "echo mine"


def test_G18_1_second_apply_changes_nothing_and_keeps_the_original(world):
    home, pb = world
    settings(home, {"statusLine": {"type": "command", "command": "echo mine"}})
    run("setup", "--minimal", "--apply")
    code, out, _ = run("setup", "--minimal", "--apply")
    assert code == 0 and out.endswith("Nothing to change.\n")
    assert S.original_from_wrapper(str(pb / "statusline.sh")) == "echo mine"   # never wraps itself
    assert len([n for n in os.listdir(home / ".claude") if ".bak-" in n]) == 1


def test_G18_1_existing_config_is_kept(world):
    home, pb = world
    pb.mkdir(mode=0o700)
    (pb / "config.json").write_text('{"operator_name": "Grant"}')
    run("setup", "--minimal", "--apply")
    assert json.loads((pb / "config.json").read_text()) == {"operator_name": "Grant"}


def test_G18_1_no_settings_file_and_bad_settings(world):
    home, pb = world
    assert run("setup", "--minimal", "--apply")[0] == 0
    assert settings(home)["statusLine"]["command"] == str(pb / "statusline.sh")
    (home / ".claude" / "settings.json").write_text("[1]")
    code, _, err = run("setup", "--minimal")
    assert code == 6 and "not a JSON object" in err


def _install_fake_version(home):
    """A plugin version folder that is this checkout, recorded in installed_plugins.json."""
    v = home / ".claude" / "plugins" / "cache" / "thewindstorm" / "windstorm-pit-board" / "0.1.0"
    shutil.copytree(os.path.join(ROOT, "pitboard"), v / "pitboard",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps(
        {"version": 2, "plugins": {"windstorm-pit-board@thewindstorm": [
            {"scope": "user", "installPath": str(v), "version": "0.1.0"}]}}))


@pytest.mark.parametrize("own", ["printf 'MINE'", "printf 'L1\\nL2'", None])
def test_G10_5_wrapper_joins_the_operator_line_and_the_segment(world, own):
    home, pb = world
    if own:
        settings(home, {"statusLine": {"type": "command", "command": own}})
    run("setup", "--minimal", "--apply")
    _install_fake_version(home)
    env = dict(os.environ, HOME=str(home), PITBOARD_LANE="api")
    env.pop("PITBOARD_HOME")                                     # the wrapper sets it itself
    wrap = str(pb / "statusline.sh")

    def line():
        return subprocess.run([wrap], input='{"session_id": "x"}', capture_output=True, text=True, env=env,
                              timeout=30).stdout

    mine = {"printf 'MINE'": "MINE", "printf 'L1\\nL2'": "L1\nL2"}.get(own, "")
    assert line() == mine                                         # nothing waits: no segment
    run("add", "--lane", "api", "--title", "Go?", "--suggested", "yes")
    out = line()
    seg = "🔴 1 ask · oldest 0m"
    assert out.startswith("\x1b[31m") and seg in out             # the segment comes first
    if mine == "MINE":
        assert out.endswith(" · MINE") and "\n" not in out        # before a one-line status line
    elif mine:
        first, rest = out.split("\n", 1)                         # its own line above several lines
        assert seg in first and rest == "L1\nL2"


@pytest.mark.skipif(not (shutil.which("timeout") or shutil.which("gtimeout")), reason="no timeout command here")
@pytest.mark.parametrize("fault", ["sleep 5; printf 'LATE'", "printf 'HALF'; exit 1"])
def test_G10_5_wrapper_fails_soft_slow_or_broken_segment(world, fault):
    home, pb = world
    settings(home, {"statusLine": {"type": "command", "command": "printf 'MINE'"}})
    run("setup", "--minimal", "--apply")
    launcher = pb / "bin" / "pitboard"
    launcher.write_text("#!/bin/sh\ncat >/dev/null\n" + fault + "\n")     # a hung or broken Pit Board
    env = dict(os.environ, HOME=str(home))
    import time
    t = time.monotonic()
    out = subprocess.run([str(pb / "statusline.sh")], input='{"session_id": "x"}', capture_output=True,
                         text=True, env=env, timeout=30).stdout
    assert out == "MINE"                                         # the operator's line alone
    assert time.monotonic() - t < S.STATUS_CAP_SECONDS + 2       # the cap held (the slow one sleeps 5 s)
