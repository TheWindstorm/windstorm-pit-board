"""G6.2 `version` (plan 1.19): a second line when the home's launcher copy is older than the newest installed
version that is not bad, and no pin holds the home. The first line never changes."""
import json
import os

import pytest

from pitboard import __version__, cli, launch

V = __version__
NEW = max(V, "0.1.2", key=launch._vkey)       # the installed version: one that refreshes a copy
FIRST = f"{V} (installed {NEW}, "


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A fake HOME whose plugin registry holds this version, and a Pit Board home with a launcher copy
    from a release before 0.1.2 (no copied-from)."""
    claude = tmp_path / "home" / ".claude"
    (claude / "plugins").mkdir(parents=True)
    (claude / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
        "windstorm-pit-board@mk": [{"scope": "user", "version": NEW,
                                    "installPath": str(claude / "plugins" / "cache" / "mk" / "windstorm-pit-board" / NEW)}]}}))
    pb = tmp_path / "pb"
    for rel in (os.path.join("bin", "pitboard"), os.path.join("pitboard", "launch.py")):
        (pb / rel).parent.mkdir(parents=True, exist_ok=True)
        (pb / rel).write_text("# an older launcher\n")
    (pb / "update").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PITBOARD_HOME", str(pb))
    monkeypatch.delenv("PITBOARD_SELF_UPDATE", raising=False)
    return pb


def lines(out):
    """The version lines without the last one, which always names what the status line runs (P15)."""
    *rest, last = out.message.split("\n")
    assert last.startswith("status line runs"), last
    return rest


def test_G6_2_version_says_when_the_launcher_copy_is_older(home):
    out = cli.cmd_version(None)
    assert lines(out)[0].startswith(FIRST)
    assert lines(out)[1:] == ["launcher copy from before-0.1.2; the next session start refreshes it"]
    (home / "pitboard" / "copied-from").write_text("0.1.1\n")
    assert lines(cli.cmd_version(None))[1:] == ["launcher copy from 0.1.1; the next session start refreshes it"]


def test_G6_2_version_with_self_update_off_says_no_start_refreshes_it(home):
    (home / "config.json").write_text(json.dumps({"self_update": False}))
    assert lines(cli.cmd_version(None))[1:] == ["launcher copy from before-0.1.2; self_update is off, so no start refreshes it"]


def test_G6_2_version_has_no_second_line_while_a_pin_holds_the_home(home):
    """A pinned home's hooks run the pinned version, which may have no refresh: the line would be false."""
    (home / "update" / "pin").write_text("0.1.0\n")
    out = cli.cmd_version(None)
    assert lines(out) == [lines(out)[0]] and "pinned 0.1.0" in lines(out)[0]


def test_G6_2_version_has_no_second_line_when_the_newest_install_is_bad(home):
    """The refresh never runs from a bad version: the line would be false."""
    (home / "update" / "bad-versions").write_text(NEW + "\n")
    out = cli.cmd_version(None)
    assert lines(out) == [lines(out)[0]] and lines(out)[0].startswith(FIRST)


def test_G6_2_version_has_one_line_for_an_up_to_date_copy_or_none(home):
    (home / "pitboard" / "copied-from").write_text(NEW + "\n")
    assert len(lines(cli.cmd_version(None))) == 1
    (home / "pitboard" / "copied-from").write_text("9.9.9\n")                  # newer than any install: not older
    assert len(lines(cli.cmd_version(None))) == 1
    os.remove(home / "pitboard" / "launch.py")                                 # no whole copy: setup makes one
    assert len(lines(cli.cmd_version(None))) == 1


def test_G6_2_the_second_line_never_fails_the_version_line(home, monkeypatch):
    """G21.4's refresh checks a new launcher by its `version` exit code: a broken config must not fail it."""
    def broken():
        raise ValueError("unreadable config")
    monkeypatch.setattr(cli.store, "config", broken)
    out = cli.cmd_version(None)
    assert out.code == 0 and lines(out) == [lines(out)[0]] and lines(out)[0].startswith(FIRST)
