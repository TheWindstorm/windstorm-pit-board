"""G18.1: pitboard setup --minimal (config, stable launcher copy, status line wrapper)."""
import io
import json
import os
import shutil
import stat
import subprocess

import pytest

from pitboard import cli, setup as S

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
        "1. config file", "2. stable launcher copy", "3. stable launcher copy", "4. status line wrapper",
        "5. status line setting"]
    assert not pb.exists() and (home / ".claude" / "settings.json").read_bytes() == before


def test_G18_1_full_setup_waits_for_0_2_0(world):
    code, _, err = run("setup")
    assert code == 2 and "--minimal" in err


def test_G18_1_apply_writes_everything_with_backups(world):
    home, pb = world
    settings(home, {"statusLine": {"type": "command", "command": "echo mine", "padding": 1}, "model": "x"})
    code, out, _ = run("setup", "--minimal", "--apply")
    assert code == 0 and out.endswith("Done: 5 change(s).\n")
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


@pytest.mark.parametrize("own", ["printf 'MINE'", None])
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

    assert line() == ("MINE" if own else "")                      # nothing waits: no segment
    run("add", "--lane", "api", "--title", "Go?", "--suggested", "yes")
    out = line()
    seg = "🔴 1 ask · oldest 0m"
    assert seg in out and (out.startswith("MINE · ") if own else out.startswith("\x1b[31m"))
