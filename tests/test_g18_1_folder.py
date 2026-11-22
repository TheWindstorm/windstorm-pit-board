"""G18.1 folder mode: pitboard setup --folder (one folder's own settings, never the user's; promises P5 and P6)."""
import hashlib
import io
import json
import os
import stat

import pytest

from pitboard import cli, folder as F, setup as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = F.PLUGIN

# A stand-in for `claude plugin install|uninstall --scope local`: like the real one, it writes (or
# removes) the plugin's key under enabledPlugins in the folder's .claude/settings.local.json.
STAND_IN = r'''#!/usr/bin/env python3
import json, os, sys
log = os.environ["STAND_IN_LOG"]
with open(log, "a") as f:
    f.write(" ".join(sys.argv[1:]) + " in " + os.getcwd() + "\n")
if os.environ.get("STAND_IN_FAIL"):
    print("stand-in: install failed on purpose"); sys.exit(1)
if sys.argv[1:3] in (["plugin", "install"], ["plugin", "uninstall"]):
    ls = os.path.join(os.getcwd(), ".claude", "settings.local.json")
    d = json.load(open(ls)) if os.path.exists(ls) and open(ls).read().strip() else {}
    ep = d.setdefault("enabledPlugins", {})
    if sys.argv[2] == "install":
        ep[sys.argv[3]] = True
    else:
        ep.pop(sys.argv[3], None)
        if not ep: d.pop("enabledPlugins")
    os.makedirs(os.path.dirname(ls), exist_ok=True)
    json.dump(d, open(ls, "w"), indent=2)
'''


@pytest.fixture
def world(tmp_path, monkeypatch):
    home, pb, lane = tmp_path / "home", tmp_path / "home" / ".pitboard", tmp_path / "work" / "lane"
    (home / ".claude").mkdir(parents=True)
    lane.mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text('{"statusLine": {"type": "command", "command": "my-line"}}')
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "claude").write_text(STAND_IN)
    (bindir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("STAND_IN_LOG", str(tmp_path / "calls.log"))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("PITBOARD_HOME", raising=False)
    monkeypatch.delenv("STAND_IN_FAIL", raising=False)
    monkeypatch.setattr(F, "sessions_in", lambda folder, ps_lines=None, cwd_of=None: [])
    return home, pb, lane


def ls_of(lane):
    return lane / ".claude" / "settings.local.json"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    return cli.main(list(argv), stdout=out, stderr=err), out.getvalue(), err.getvalue()


def test_G18_1_folder_refuses_the_home_folder(world):
    home, pb, lane = world
    with pytest.raises(F.Refused, match="home folder"):
        F.apply(str(home), root=ROOT)
    assert not (home / ".claude" / F.RECORD).exists()


def test_G18_1_folder_refuses_a_folder_where_two_sessions_run(world):
    home, pb, lane = world
    with pytest.raises(F.Refused, match="2 Claude Code sessions"):
        F.apply(str(lane), root=ROOT, sessions=[101, 102])
    assert not (lane / ".claude").exists()


def test_G18_1_folder_counts_sessions_by_their_command_on_macos(tmp_path):
    """P6: on macOS a session's process name is its version file (2.1.330); its command is still claude."""
    lane = tmp_path / "lane"
    lane.mkdir()
    ps = ["  101 claude --model claude-haiku-5-5 -n one",            # macOS: comm is 2.1.330, args say claude
          "  102 /Users/a/.local/bin/claude --resume 5f0c",          # started by its full path
          "  103 /bin/zsh -l",                                        # the shell around it: not a session
          "  104 python3 claude-helper.py",                           # a word that only starts with claude
          "  105 claude --name elsewhere"]                            # a session in another folder
    cwd = {101: str(lane), 102: str(lane), 103: str(lane), 104: str(lane), 105: str(tmp_path)}
    found = F.sessions_in(str(lane), ps_lines=ps, cwd_of=lambda pid: os.path.realpath(cwd[pid]))
    assert found == [101, 102]
    with pytest.raises(F.Refused, match="2 Claude Code sessions"):
        F.check(str(lane), sessions=found)


@pytest.mark.parametrize("before, why", [
    ('{"statusLine": {"type": "command", "command": "x"}}', "its own statusLine"),
    ('{"env": {"PITBOARD_HOME": "/elsewhere"}}', "another PITBOARD_HOME"),
    ('["not", "an", "object"]', "not a JSON object"),
    ('{"enabledPlugins": {"%s": false}}' % PLUGIN, "already set"),
])
def test_G18_1_folder_refuses_settings_it_must_not_change(world, before, why):
    home, pb, lane = world
    (lane / ".claude").mkdir()
    ls_of(lane).write_text(before)
    with pytest.raises(F.Refused, match=why):
        F.apply(str(lane), root=ROOT)
    assert ls_of(lane).read_text() == before and not (lane / ".claude" / F.RECORD).exists()


def test_G18_1_folder_plan_changes_nothing(world):
    home, pb, lane = world
    rc, out, err = run("setup", "--folder", str(lane))
    assert rc == 0, err
    assert "local scope" in out and "Nothing changed" in out
    assert not (lane / ".claude").exists() and not pb.exists()


def test_G18_1_folder_undo_puts_the_folder_back_byte_for_byte(world):
    """P5: the home is made without the user's settings; the folder's file comes back byte for byte."""
    home, pb, lane = world
    (lane / ".claude").mkdir()
    ls_of(lane).write_text('{"env":{"X":"1"},  "permissions": {"allow": []}}')   # odd spacing on purpose
    before, user_before = sha(ls_of(lane)), sha(home / ".claude" / "settings.json")
    F.apply(str(lane), root=ROOT)
    d = json.loads(ls_of(lane).read_text())
    assert d["statusLine"]["command"] == S.wrapper_path(str(pb)) and d["enabledPlugins"] == {PLUGIN: True}
    assert d["env"] == {"X": "1"}                       # the default home: no PITBOARD_HOME written
    assert (pb / "bin" / "pitboard").exists() and (pb / "statusline.sh").exists()
    assert sha(home / ".claude" / "settings.json") == user_before   # never the user's settings
    F.undo(str(lane))
    assert sha(ls_of(lane)) == before and not (lane / ".claude" / F.RECORD).exists()
    assert sha(home / ".claude" / "settings.json") == user_before


def test_G18_1_folder_undo_of_a_folder_with_no_settings_leaves_nothing(world):
    home, pb, lane = world
    F.apply(str(lane), root=ROOT)
    assert ls_of(lane).exists()
    F.undo(str(lane))
    assert not (lane / ".claude").exists()


def test_G18_1_folder_undo_keeps_what_another_tool_added_since(world):
    home, pb, lane = world
    F.apply(str(lane), root=ROOT)
    d = json.loads(ls_of(lane).read_text())
    d["env"] = {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "150000"}    # another skill's tuner, after us
    ls_of(lane).write_text(json.dumps(d))
    (lane / ".claude" / "settings.local.json.bak-other").write_text("{}")
    F.undo(str(lane))
    assert json.loads(ls_of(lane).read_text()) == {"env": {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "150000"}}
    assert (lane / ".claude" / "settings.local.json.bak-other").exists()


def test_G18_1_folder_another_home_rides_in_the_folder_env(world, tmp_path, monkeypatch):
    """A home other than the default is written into the folder's env, so a session brought back keeps it."""
    home, pb, lane = world
    other = str(tmp_path / "home-two")
    monkeypatch.setenv("PITBOARD_HOME", other)
    F.apply(str(lane), root=ROOT)
    d = json.loads(ls_of(lane).read_text())
    assert d["env"] == {"PITBOARD_HOME": other} and d["statusLine"]["command"] == os.path.join(other, "statusline.sh")
    monkeypatch.delenv("PITBOARD_HOME")                 # the undo reads the home from the record
    F.undo(str(lane))
    assert not (lane / ".claude").exists()


def test_G18_1_folder_undo_keeps_a_home_the_person_set_before(world, tmp_path, monkeypatch):
    home, pb, lane = world
    other = str(tmp_path / "home-two")
    monkeypatch.setenv("PITBOARD_HOME", other)
    (lane / ".claude").mkdir()
    ls_of(lane).write_text(json.dumps({"env": {"PITBOARD_HOME": other}}))
    before = sha(ls_of(lane))
    F.apply(str(lane), root=ROOT)
    F.undo(str(lane))
    assert sha(ls_of(lane)) == before


def test_G18_1_folder_a_failed_install_is_undone(world, monkeypatch):
    home, pb, lane = world
    (lane / ".claude").mkdir()
    ls_of(lane).write_text('{"env": {"X": "1"}}')
    before = sha(ls_of(lane))
    monkeypatch.setenv("STAND_IN_FAIL", "1")
    with pytest.raises(RuntimeError, match="install failed.*undone"):
        F.apply(str(lane), root=ROOT)
    assert sha(ls_of(lane)) == before and not (lane / ".claude" / F.RECORD).exists()


def test_G18_1_folder_cli_undo_needs_a_folder(world):
    rc, out, err = run("setup", "--undo")
    assert rc == 2 and "--folder" in err


def test_G18_1_folder_a_plugin_already_installed_here_is_not_installed_again(world, tmp_path):
    """Run from the installed copy after `claude plugin install` in the folder: step 3 is skipped."""
    home, pb, lane = world
    reg = home / ".claude" / "plugins" / "installed_plugins.json"
    reg.parent.mkdir(parents=True)
    reg.write_text(json.dumps({"version": 2, "plugins": {PLUGIN: [
        {"scope": "local", "projectPath": str(lane), "installPath": "/x/0.1.1", "version": "0.1.1"}]}}))
    F.apply(str(lane), root=ROOT)
    calls = (tmp_path / "calls.log").read_text() if (tmp_path / "calls.log").exists() else ""
    assert "plugin install" not in calls
    assert json.loads(ls_of(lane).read_text())["statusLine"]["command"] == S.wrapper_path(str(pb))
