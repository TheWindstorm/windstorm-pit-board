"""P15 (plan 1.25, G21.4): which version ran is read, never worked out.

Seen 2026-11-23: one lane's `claude plugin update` changed what the other lanes' status lines ran within a second,
and nothing in the log showed it. Every hook line now ends with `v=<version> step=<n>`, and `pitboard version`
has a last line naming what the status line (the home's launcher copy) runs."""
import json
import os
import shutil
import subprocess

import pytest

from pitboard import __version__ as V, cli, hooks

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path / "home"), PITBOARD_HOME=str(tmp_path / "pb"))
    for k in ("PITBOARD_LAUNCH_STEP", "PITBOARD_SELF_UPDATE", "PITBOARD_LANE", "CLAUDE_ENV_FILE"):
        env.pop(k, None)
    (tmp_path / "home").mkdir()
    return env


@pytest.mark.skipif(os.name == "nt", reason="bin/pitboard is a POSIX shell script")
def test_G21_4_every_hook_line_names_the_version_and_the_step(tmp_path):
    """Through the real launcher, as a hook runs: with nothing installed it runs its own folder (step 5)."""
    env = _env(tmp_path)
    for name, inp in (("stop", {"session_id": "s1"}), ("user-prompt-submit", {"session_id": "s1", "prompt": "hello"})):
        r = subprocess.run([os.path.join(ROOT, "bin", "pitboard"), "hook", name], input=json.dumps(inp), text=True,
                           capture_output=True, env=env, timeout=60)
        assert r.returncode == 0 and r.stderr == ""
    log = (tmp_path / "pb" / "logs" / "pitboard.log").read_text().splitlines()
    assert len(log) == 2 and all(ln.endswith(f" v={V} step=5") for ln in log), log


def test_G21_4_a_line_from_an_older_launcher_says_its_step_is_unknown(tmp_path, monkeypatch):
    monkeypatch.setenv("PITBOARD_HOME", str(tmp_path / "pb"))
    monkeypatch.delenv("PITBOARD_LAUNCH_STEP", raising=False)        # a launcher before 0.1.3 sets nothing
    hooks.log("stop", "api-server", "idle")
    assert (tmp_path / "pb" / "logs" / "pitboard.log").read_text().endswith(f" stop api-server idle v={V} step=?\n")


@pytest.fixture
def copy_home(tmp_path, monkeypatch):
    """A HOME whose registry holds this checkout as the installed version, and a Pit Board home with this
    checkout's launcher as its copy (the one the status line calls)."""
    claude = tmp_path / "home" / ".claude" / "plugins"
    claude.mkdir(parents=True)
    (claude / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
        "windstorm-pit-board@mk": [{"scope": "local", "version": V, "installPath": ROOT}]}}))
    pb = tmp_path / "pb"
    (pb / "pitboard").mkdir(parents=True)
    shutil.copy(os.path.join(ROOT, "pitboard", "launch.py"), pb / "pitboard" / "launch.py")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PITBOARD_HOME", str(pb))
    monkeypatch.delenv("PITBOARD_SELF_UPDATE", raising=False)
    return pb


def last(out):
    return out.message.split("\n")[-1]


def test_G21_4_version_names_what_the_status_line_runs(copy_home):
    assert last(cli.cmd_version(None)) == f"status line runs {V} (step 6)"     # the first installed entry
    (copy_home / "update").mkdir()
    (copy_home / "update" / "good-versions").write_text(V + "\n")
    assert last(cli.cmd_version(None)) == f"status line runs {V} (step 3)"     # a version that passed its check
    out = cli.cmd_version(None)
    assert out.code == 0 and set(out.data) == {"running", "installed", "pinned", "generation"}


def test_G21_4_the_status_line_line_never_fails_version(copy_home):
    os.remove(copy_home / "pitboard" / "launch.py")
    assert last(cli.cmd_version(None)) == "status line runs: no launcher copy in this home"
    (copy_home / "pitboard" / "launch.py").write_text("# a broken copy\n")
    out = cli.cmd_version(None)
    assert out.code == 0 and last(out) == "status line runs: unknown (AttributeError)"
    (copy_home / "pitboard" / "launch.py").write_text("raise SystemExit(3)\n")
    out = cli.cmd_version(None)
    assert out.code == 0 and last(out).startswith("status line runs: unknown")
