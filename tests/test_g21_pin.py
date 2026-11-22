"""G21.10 before the rest of the updater (P10, plan 1.15): pitboard self-update --pin VER and --unpin.
And G6.2: `pitboard update` only ever changes an ask; it is refused, naming self-update, otherwise."""
import io
import json
import os
import shutil
import subprocess
import sys

import pytest

from pitboard import cli, launch as L

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCH = os.path.join(ROOT, "pitboard", "launch.py")


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A fake HOME whose plugin cache holds 0.1.0 and 0.1.1 (both installed, 0.1.1 newest) and a Pit Board home
    with a stable launcher copy."""
    home, pb = tmp_path / "home", tmp_path / "pb"
    claude = home / ".claude"
    folders = {}
    for v in ("0.1.0", "0.1.1"):
        f = claude / "plugins" / "cache" / "mk" / L.PLUGIN / v
        (f / "pitboard").mkdir(parents=True)
        (f / "pitboard" / "__init__.py").write_text("")
        (f / "pitboard" / "cli.py").write_text("def main():\n    print('ran %s')\n    return 0\n" % v)
        folders[v] = str(f)
    (claude / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
        f"{L.PLUGIN}@mk": [{"scope": "local", "installPath": folders[v], "version": v} for v in ("0.1.0", "0.1.1")]}}))
    (pb / "pitboard").mkdir(parents=True)
    shutil.copy(LAUNCH, pb / "pitboard" / "launch.py")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PITBOARD_HOME", str(pb))
    monkeypatch.delenv("PITBOARD_SELF_UPDATE", raising=False)
    return home, pb, folders


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def stable(pb, *args):
    """The stable copy as the status line wrapper runs it."""
    env = dict(os.environ)
    r = subprocess.run([sys.executable, "-I", str(pb / "pitboard" / "launch.py"), *args], capture_output=True,
                       text=True, env=env, timeout=60)
    return r.stdout.strip()


def test_G21_10_pin_holds_a_home_on_a_chosen_version(world):
    home, pb, folders = world
    assert stable(pb, "status") == "ran 0.1.1"                       # the highest install (G21.4 step 6)
    code, out, _ = run("self-update", "--pin", "0.1.0")
    assert code == 0 and "pinned 0.1.0" in out and (pb / "update" / "pin").read_text() == "0.1.0\n"
    assert stable(pb, "status") == "ran 0.1.0"                       # the status line follows at its next call
    assert L.choose(own_root=folders["0.1.1"]) == (folders["0.1.0"], 1)   # and so do a 0.1.1 folder's hooks
    code, out, _ = run("self-update", "--unpin")
    assert code == 0 and "pinned" not in out and not (pb / "update" / "pin").exists()
    assert stable(pb, "status") == "ran 0.1.1"
    assert run("self-update", "--unpin")[0] == 0                     # releasing twice is fine


def test_G21_4_self_update_skips_the_pin_so_an_old_pin_can_be_released(world):
    """Plan 1.18: pinned to a version that has no self-update, every launcher runs that version, so
    self-update alone starts at step 2 (here the fake 0.1.1 answers, standing in for the newest)."""
    home, pb, folders = world
    run("self-update", "--pin", "0.1.0")
    assert stable(pb, "status") == "ran 0.1.0" and stable(pb, "self-update", "--unpin") == "ran 0.1.1"
    assert L.choose(own_root=folders["0.1.1"], skip_pin=True) == (folders["0.1.1"], 5)
    assert L.choose(skip_pin=True) == (folders["0.1.1"], 6)


def test_G21_4_unpin_through_the_stable_copy_from_an_old_pin_prints_the_version_line(tmp_path, monkeypatch):
    """Plan 1.18 with this real code as the newest install and a 0.1.0 that has no self-update, pinned."""
    from pitboard import __version__ as V
    home, pb = tmp_path / "home", tmp_path / "pb"
    cache = home / ".claude" / "plugins" / "cache" / "mk" / L.PLUGIN
    new, old = cache / V, cache / "0.1.0"
    for d in ("pitboard", "bin", "hooks"):
        shutil.copytree(os.path.join(ROOT, d), new / d, ignore=shutil.ignore_patterns("__pycache__"))
    (old / "pitboard").mkdir(parents=True)
    (old / "pitboard" / "__init__.py").write_text("")
    (old / "pitboard" / "cli.py").write_text("import sys\ndef main():\n    print('0.1.0 has no', sys.argv[1:])\n    return 2\n")
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
        f"{L.PLUGIN}@mk": [{"scope": "local", "installPath": str(p), "version": v} for p, v in ((old, "0.1.0"), (new, V))]}}))
    (pb / "pitboard").mkdir(parents=True)
    (pb / "bin").mkdir()
    shutil.copy(LAUNCH, pb / "pitboard" / "launch.py")
    shutil.copy(os.path.join(ROOT, "bin", "pitboard"), pb / "bin" / "pitboard")
    (pb / "update").mkdir()
    (pb / "update" / "pin").write_text("0.1.0\n")
    env = dict(os.environ, HOME=str(home), PITBOARD_HOME=str(pb))
    env.pop("PITBOARD_SELF_UPDATE", None)
    sh = lambda *a: subprocess.run([str(pb / "bin" / "pitboard"), *a], capture_output=True, text=True, env=env,
                                   timeout=60)
    r = sh("version")
    assert r.stdout.startswith("0.1.0 has no")                                  # pinned: the status line runs 0.1.0
    r = sh("self-update", "--unpin")
    assert r.returncode == 0 and r.stdout.startswith(f"{V} (installed {V}, hooks gen ") and "pinned" not in r.stdout
    assert not (pb / "update" / "pin").exists()
    assert sh("version").stdout.startswith(f"{V} (installed {V}")                # and then runs the newest


@pytest.mark.parametrize("ver, why", [
    ("0.2.0", "no runnable 0.2.0 in the plugin cache"),
    ("latest", "not a version: latest"),
])
def test_G21_10_pin_refuses_a_version_it_cannot_run(world, ver, why):
    home, pb, folders = world
    code, out, err = run("self-update", "--pin", ver)
    assert code == 2 and why in err and "Nothing changed." in err and out == ""
    assert not (pb / "update" / "pin").exists()


def test_G21_10_pin_refuses_a_bad_version_and_keeps_the_old_pin(world):
    home, pb, folders = world
    run("self-update", "--pin", "0.1.1")
    (pb / "update" / "bad-versions").write_text("0.1.0\n")
    code, _, err = run("self-update", "--pin", "0.1.0")
    assert code == 2 and "0.1.0 is in update/bad-versions" in err
    assert (pb / "update" / "pin").read_text() == "0.1.1\n"


def test_G21_10_pin_json_has_the_version_object(world):
    code, out, _ = run("self-update", "--pin", "0.1.0", "--json")
    d = json.loads(out)
    assert code == 0 and d["ok"] and d["data"]["pinned"] == "0.1.0" and set(d["data"]) == {
        "running", "installed", "pinned", "generation"}


@pytest.mark.parametrize("argv", [["self-update"], ["self-update", "--check"], ["self-update", "--now"]])
def test_G21_10_the_rest_of_the_updater_is_not_built_yet(world, argv):
    home, pb, folders = world
    code, _, err = run(*argv)
    assert code == 2 and "0.2.0" in err and "--pin VER and --unpin" in err
    assert not (pb / "update").exists()


def test_G21_10_pin_and_unpin_together_are_refused(world):
    assert run("self-update", "--pin", "0.1.0", "--unpin")[0] == 2


@pytest.mark.parametrize("argv", [
    ["update"],
    ["update", "--title", "x"],
    ["update", "--pin", "0.1.0"],
    ["update", "--check"],
    ["update", "A1", "--unpin"],
    ["update", "A1", "--now"],
])
def test_G6_2_update_never_updates_pit_board(world, argv):
    home, pb, folders = world
    code, out, err = run(*argv)
    assert code == 2 and out == "" and "self-update" in err and len(err.rstrip("\n").split("\n")) == 1
    assert len(err.rstrip("\n")) <= 100 and not (pb / "update").exists()
