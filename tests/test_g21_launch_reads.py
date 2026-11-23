"""G21.4 (plan 1.29, P19): three answers for the reads the launcher's choice of version hangs on.

update/bad-versions, update/pin, update/good-versions and Claude Code's plugin registry each answer yes, no (missing)
or could not be read. On could not be read the launcher does not move to another version on this pass: it runs only
its own version folder, or nothing, and says which read failed. An unreadable bad-versions used to read as empty,
so a version marked bad could run."""
import os

import pytest

from pitboard import launch as L
from test_g21_launch import pick, world  # noqa: F401  (the fixture)

READS = ["good-versions", "bad-versions", "pin", "registry"]


def _break(w, which):
    """Make one read fail: a folder where the file should be cannot be read as one."""
    path = (w.claude / "plugins" / "installed_plugins.json") if which == "registry" else (w.pb / "update" / which)
    if path.exists():
        path.unlink()
    path.mkdir()
    return str(path)


@pytest.fixture
def two(world):
    """0.2.0 installed and marked bad; 0.1.0 is this hook's own folder."""
    old, new = world.version("0.1.0"), world.version("0.2.0")
    world.install(new, "0.2.0")
    world.lines("good-versions", "0.1.0", "0.2.0")
    world.lines("bad-versions", "0.2.0")
    world.lines("pin", "0.1.0")
    return world, old, new


@pytest.mark.parametrize("which", READS)
def test_G21_4_a_read_that_fails_moves_to_no_other_version(two, which):
    w, old, new = two
    path = _break(w, which)
    assert pick(w, own=old) == (old, 5)                       # its own folder, and nothing else
    assert [p for p, _ in L.UNREAD] == [path]
    assert pick(w, own=str(w.pb)) == (None, 7)                 # the stable copy has no folder of its own: nothing
    assert pick(w, own=new) == (new, 5)                       # a hook of 0.2.0 keeps running 0.2.0: no move either way


def test_G21_4_an_unreadable_bad_versions_never_runs_the_bad_version(two):
    """The fault this row is for: before P19 the stable copy read an unreadable bad-versions as empty and ran 0.2.0."""
    w, old, new = two
    (w.pb / "update" / "pin").unlink()
    w.lines("good-versions")
    w.lines("bad-versions")
    assert pick(w, own=str(w.pb)) == (new, 6)                 # control: not marked bad, the stable copy runs 0.2.0
    w.lines("bad-versions", "0.2.0")
    assert pick(w, own=str(w.pb)) == (None, 7)                # marked bad: never
    path = _break(w, "bad-versions")
    assert pick(w, own=str(w.pb)) == (None, 7)                # unreadable: never either (it read as empty before P19)
    assert L.UNREAD == [(path, "IsADirectoryError")]


def test_G21_4_missing_is_no_not_could_not_be_read(world):
    a = world.version("0.1.0")
    world.install(a, "0.1.0")
    assert pick(world) == (a, 6) and L.UNREAD == []
    os.remove(world.claude / "plugins" / "installed_plugins.json")
    assert pick(world) == (None, 7) and L.UNREAD == []
    (world.claude / "plugins" / "installed_plugins.json").write_text("[1, 2]")       # not an object of plugins
    assert pick(world) == (None, 7) and L.UNREAD and "not a JSON object" in L.UNREAD[0][1]


@pytest.mark.parametrize("which", READS)
def test_G21_4_what_each_entry_point_says_when_a_read_fails(world, which, capsys, monkeypatch):
    a = world.version("0.1.0")
    world.install(a, "0.1.0")
    path = _break(world, which)
    monkeypatch.setattr(L, "__file__", str(world.pb / "pitboard" / "launch.py"))     # run as the stable copy
    (world.pb / "logs").mkdir()
    assert L.main(["hook", "session-start"]) == 0
    assert capsys.readouterr() == ("", "")
    log = (world.pb / "logs" / "pitboard.log").read_text()
    assert f"session-start - launcher could not read {path} (IsADirectoryError" in log and log.endswith("; nothing run\n")
    assert L.main(["status"]) == 0 and capsys.readouterr() == ("", "")
    assert L.main(["version"]) == 1
    assert capsys.readouterr().err.startswith(f"pitboard: could not read {path} (")


def test_G21_4_a_hook_that_runs_its_own_folder_names_the_failed_read(two, monkeypatch, capsys):
    """When the launcher could not read something but runs the hook's own folder, the hook's log line says so."""
    from pitboard import hooks
    monkeypatch.delenv("PITBOARD_LAUNCH_UNREAD", raising=False)
    monkeypatch.setenv("PITBOARD_LAUNCH_STEP", "5")
    monkeypatch.setenv("PITBOARD_LAUNCH_UNREAD", "/x/update/bad-versions (PermissionError)")
    hooks.log("session-start", "k", "source=resume")
    line = (two[0].pb / "logs" / "pitboard.log").read_text().splitlines()[-1]
    assert line.endswith(" step=5 unread=/x/update/bad-versions (PermissionError)")
