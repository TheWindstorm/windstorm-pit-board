"""G18.3 `pitboard uninstall` (plan 1.28, P17): one way of leaving; what is the person's stays and is counted."""
import ast
import fcntl
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading

import pytest

from pitboard import cli, leave as L

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MINE = {"statusLine": {"type": "command", "command": "echo mine", "padding": 1}, "model": "x"}
MINE_TEXT = json.dumps(MINE, indent=4) + "\n"          # the person's own layout: byte for byte means this
NOT_ROOT = pytest.mark.skipif(os.geteuid() == 0, reason="root reads a file with mode 000")


class Tty(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A fake HOME: the person's own status line, Pit Board set up by `setup --minimal --apply`, and one lane log
    with two asks (one open), as a session would leave it."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    st = home / ".claude" / "settings.json"
    st.write_text(MINE_TEXT)
    os.chmod(st, 0o644)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("PITBOARD_HOME", raising=False)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")         # no `claude` here unless a test puts one
    assert run_cli("setup", "--minimal", "--apply")[0] == 0
    pb = home / ".pitboard"
    (pb / "lanes").mkdir(exist_ok=True)
    (pb / "lanes" / "api.jsonl").write_text("".join(json.dumps(e) + "\n" for e in (
        {"type": "asked", "uid": "u1"}, {"type": "asked", "uid": "u2"}, {"type": "done", "uid": "u2"})))
    (pb / "lanes" / "api.lock").write_text("")
    (pb / "logs").mkdir(exist_ok=True)
    (pb / "logs" / "pitboard.log").write_text("2026-11-23T00:00:00.000Z session-start api started v=0.1.3 step=5\n")
    return home, pb, st


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    return cli.main(list(argv), stdout=out, stderr=err), out.getvalue(), err.getvalue()


def run(*argv, stdin=None, stdout=None, calls=None, fail=False, effect=None):
    """leave.main with a stand-in for `claude`: records each call; fail=True answers exit 1; effect(args) is what
    the stand-in does to the home before it answers."""
    out, err = stdout or io.StringIO(), io.StringIO()

    def fake(args, **kw):
        if calls is not None:
            calls.append((args, kw.get("cwd")))
        if effect is not None and not fail:
            effect(args)
        return subprocess.CompletedProcess(args, 1 if fail else 0, "", "stand-in: failed on purpose\n" if fail else "")
    code = L.main(list(argv), stdin=stdin or io.StringIO(""), stdout=out, stderr=err, run=fake)
    return code, out.getvalue(), err.getvalue()


def tree(path):
    out = {}
    for d, _, files in os.walk(path):
        for n in files:
            p = os.path.join(d, n)
            with open(p, "rb") as f:
                out[os.path.relpath(p, path)] = (hashlib.sha256(f.read()).hexdigest(), os.stat(p).st_mode)
    return out


def registry(home, rows):
    p = home / ".claude" / "plugins" / "installed_plugins.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": 2, "plugins": {"windstorm-pit-board@thewindstorm": rows} if rows is not None
                             else {}}))
    return p


DELETE = re.compile(r"(^|[\s;&|`(])(rm|rmdir|unlink|shred)\s|rmtree|\s-delete(\s|$)")   # P48: a printed delete


def census(out):
    return out.split("census:\n", 1)[1].splitlines()     # the count prompt has no newline: the person's Enter


# ---------------------------------------------------------------- the plan, the apply, the census

def test_G18_3_plan_changes_nothing(world):
    home, pb, st = world
    before = tree(home)
    code, out, _ = run()
    assert code == 0 and tree(home) == before
    assert "pitboard uninstall: the plan (nothing changes without --apply)" in out
    assert "  would go: status line setting in ~/.claude/settings.json (put back byte for byte)" in out
    assert "  would go: ~/.pitboard/bin" in out and out.endswith("Nothing changed. Run again with --apply to do it.\n")


def test_G18_3_apply_puts_the_setting_back_byte_for_byte_and_keeps_the_persons_things(world):
    home, pb, st = world
    backups = sorted(n for n in os.listdir(home / ".claude") if n.startswith("settings.json.bak-"))
    code, out, _ = run("--apply")
    assert code == 0, out
    assert st.read_text() == MINE_TEXT and oct(os.stat(st).st_mode & 0o777) == oct(0o644)
    assert sorted(os.listdir(pb)) == ["lanes", "logs"]
    assert os.listdir(pb / "lanes") == ["api.jsonl"]                                  # its lock file went
    assert sorted(n for n in os.listdir(home / ".claude") if ".bak-" in n) == backups and backups   # yours
    rows = census(out)
    assert "  gone: status line setting in ~/.claude/settings.json (put back byte for byte)" in rows
    assert "  gone: ~/.pitboard/bin" in rows and "  gone: ~/.pitboard/statusline.sh" in rows
    assert f"  kept: 1 backup setup made of ~/.claude/settings.json (yours: ~/.claude/{backups[0]})" in rows
    assert "  kept: 2 asks (1 open) in 1 lane log, and the log of what Pit Board did in ~/.pitboard (yours)" in rows
    assert [r for r in rows if "the log of what Pit Board did" in r] == [
        "  kept: 2 asks (1 open) in 1 lane log, and the log of what Pit Board did in ~/.pitboard (yours)"]  # one row
    gone = [r for r in rows if r.startswith("  gone: ~/.pitboard/")]
    assert gone[-1] == "  gone: ~/.pitboard/setup-record.json (setup's record; last, once every step above was done)"
    assert out.splitlines()[-1] == "They are yours, to keep or delete after you look at them."   # P48: no `rm -r`


def test_G18_3_run_twice_says_nothing_of_pit_board_is_here(world):
    home, pb, st = world
    assert run("--apply")[0] == 0
    before = tree(home)
    code, out, _ = run("--apply")
    assert code == 0 and out.startswith("nothing of Pit Board is here\ncensus:\n") and tree(home) == before
    assert not [r for r in census(out) if r.startswith("  gone")]
    assert "  kept: 2 asks (1 open) in 1 lane log, and the log of what Pit Board did in ~/.pitboard (yours)" in census(out)
    assert out.splitlines()[-1] == "They are yours, to keep or delete after you look at them."


def test_G18_3_changed_since_takes_out_only_pit_boards_entry(world):
    home, pb, st = world
    d = json.loads(st.read_text())
    d["theme"] = "dark"                                  # the person changed something after setup
    st.write_text(json.dumps(d))
    code, out, _ = run("--apply")
    assert code == 0, out
    assert json.loads(st.read_text()) == dict(MINE, theme="dark")
    assert ("  gone: status line setting in ~/.claude/settings.json (Pit Board's entry taken out; the rest kept; "
            "your own status line is back)") in census(out)


def test_G18_3_a_home_from_before_the_record_uses_the_wrappers_line(world):
    home, pb, st = world
    os.remove(pb / "setup-record.json")                  # set up by 0.1.2: no record
    d = json.loads(st.read_text())
    d["theme"] = "dark"
    st.write_text(json.dumps(d))
    assert run("--apply")[0] == 0
    got = json.loads(st.read_text())
    assert got["statusLine"]["command"] == "echo mine" and got["theme"] == "dark" and got["model"] == "x"


def test_G18_3_no_status_line_before_removes_only_the_key(world, tmp_path, monkeypatch):
    home, pb, st = world
    shutil.rmtree(pb)
    st.write_text('{"model": "x"}')
    assert run_cli("setup", "--minimal", "--apply")[0] == 0
    st.write_text(json.dumps(dict(json.loads(st.read_text()), theme="dark")))
    assert run("--apply")[0] == 0
    assert json.loads(st.read_text()) == {"model": "x", "theme": "dark"}


# ---------------------------------------------------------------- three answers: each read failing in turn

def _broken_settings(home, pb, st):
    st.write_text("{not json")


def _broken_registry(home, pb, st):
    registry(home, []).write_text("{not json")


def _broken_record(home, pb, st):
    (pb / "setup-record.json").write_text("[1, 2]")


def _broken_wrapper_line(home, pb, st):
    os.remove(pb / "setup-record.json")
    st.write_text(json.dumps(dict(json.loads(st.read_text()), theme="dark")))
    w = (pb / "statusline.sh").read_text().replace(L.MARK, L.MARK + "{", 1)
    (pb / "statusline.sh").write_text(w)


def _unreadable_lane_log(home, pb, st):
    os.chmod(pb / "lanes" / "api.jsonl", 0)


def _unreadable_settings(home, pb, st):
    st.write_text(json.dumps(dict(json.loads(st.read_text()), theme="dark")))
    os.chmod(st, 0)


@NOT_ROOT
@pytest.mark.parametrize("breaks", [_broken_settings, _broken_registry, _broken_record, _broken_wrapper_line,
                                    _unreadable_lane_log, _unreadable_settings])
def test_G18_3_could_not_be_read_deletes_nothing(world, breaks):
    home, pb, st = world
    breaks(home, pb, st)
    mode = os.stat(st).st_mode
    os.chmod(st, 0o600)
    settings_before = st.read_bytes()
    os.chmod(st, mode)
    plan_code, plan_out, _ = run()
    code, out, _ = run("--apply")
    assert plan_code == code == L.INCOMPLETE, out
    assert (pb / "bin" / "pitboard").exists() and (pb / "pitboard" / "leave.py").exists()   # to run it again
    assert (pb / "lanes" / "api.jsonl").exists() and (pb / "logs" / "pitboard.log").exists()
    assert any("could not be read" in r or "has no recorded command" in r or "is not a JSON object" in r
               for r in census(out)), out
    if breaks in (_broken_settings, _broken_wrapper_line, _unreadable_settings):
        os.chmod(st, 0o600)
        assert st.read_bytes() == settings_before                        # never written when it could not be read
    os.chmod(pb / "lanes" / "api.jsonl", 0o600)


# ---------------------------------------------------------------- deleting what is kept

def test_G18_3_delete_is_refused_without_a_terminal(world):
    home, pb, st = world
    before = tree(home)
    for argv, stdin, stdout in ((["--apply", "--delete-asks-and-log"], io.StringIO("2\n"), None),
                                (["--apply", "--delete-asks-and-log"], Tty("2\n"), io.StringIO()),
                                (["--delete-asks-and-log"], Tty("2\n"), Tty())):
        code, out, err = run(*argv, stdin=stdin, stdout=stdout)
        assert code == L.USAGE and "runs only at your own terminal" in err and tree(home) == before


def test_G18_3_delete_at_a_terminal_only_when_the_count_is_typed(world):
    home, pb, st = world
    before = tree(home)
    code, out, _ = run("--apply", "--delete-asks-and-log", stdin=Tty("1\n"), stdout=Tty())
    assert code == 0 and tree(home) == before                            # a wrong count changes nothing at all
    assert "Type 2 to do both, or anything else to change nothing: " in out
    assert out.endswith("You did not type the count. Nothing changed.\n")
    code, out, _ = run("--apply", "--delete-asks-and-log", stdin=Tty("2\n"), stdout=Tty())
    assert code == 0 and not pb.exists() and st.read_text() == MINE_TEXT
    assert "  gone: your asks and the log of what Pit Board did, in ~/.pitboard (you typed the count)" in census(out)
    assert not [r for r in census(out) if r.startswith("  kept:") and "the log of what Pit Board did" in r]


def test_G18_3_delete_keeps_them_when_the_count_changed_since_it_was_typed(world, monkeypatch):
    home, pb, st = world
    real = L.uninstall

    def a_hook_adds_an_ask(**kw):
        with open(pb / "lanes" / "api.jsonl", "a") as f:
            f.write(json.dumps({"type": "asked", "uid": "u3"}) + "\n")
        return real(**kw)
    monkeypatch.setattr(L, "uninstall", a_hook_adds_an_ask)
    code, out, _ = run("--apply", "--delete-asks-and-log", stdin=Tty("2\n"), stdout=Tty())
    assert code == 0 and (pb / "lanes" / "api.jsonl").exists() and not (pb / "bin").exists()
    assert ("  kept: your asks and the log of what Pit Board did, in ~/.pitboard (there are 3 asks now, not the 2 "
            "you typed; nothing deleted)") in census(out)


# ---------------------------------------------------------------- a held lock is a wait

def _hold(path):
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def test_G18_3_a_lock_held_past_the_wait_names_the_lane_and_changes_nothing_there(world, monkeypatch):
    home, pb, st = world
    monkeypatch.setattr(L, "LOCK_WAIT_SECONDS", 0.3)
    fd = _hold(pb / "lanes" / "api.lock")
    try:
        before = tree(pb)
        code, out, _ = run("--apply")
    finally:
        os.close(fd)
    assert code == L.BUSY and tree(pb) == before
    assert ("  kept: Pit Board's files in ~/.pitboard (a session is writing to lane api now; run uninstall again in "
            "a moment)") in census(out)
    assert run("--apply")[0] == 0 and not (pb / "bin").exists()


def test_G18_3_a_lock_let_go_within_the_wait_is_only_a_wait(world, monkeypatch):
    home, pb, st = world
    monkeypatch.setattr(L, "LOCK_WAIT_SECONDS", 3)
    fd = _hold(pb / "lanes" / "api.lock")
    threading.Timer(0.3, os.close, (fd,)).start()
    code, out, _ = run("--apply")
    assert code == 0 and not (pb / "bin").exists(), out


# ---------------------------------------------------------------- the plugin installs

def test_G18_3_the_user_scope_install_is_uninstalled_after_the_settings(world):
    home, pb, st = world
    registry(home, [{"scope": "user", "version": "0.1.3", "installPath": "/x"}])
    calls = []
    code, out, _ = run("--apply", calls=calls)
    assert code == 0 and calls == [(["claude", "plugin", "uninstall", "windstorm-pit-board@thewindstorm", "--scope",
                                     "user"], str(home))]
    rows = census(out)
    assert rows.index("  gone: plugin windstorm-pit-board@thewindstorm (user scope)") > rows.index(
        "  gone: status line setting in ~/.claude/settings.json (put back byte for byte; then Claude Code's own "
        "uninstall changed its entries in that file)")


def test_G18_3_when_claude_fails_the_install_and_the_stable_copy_stay_with_the_one_command(world):
    home, pb, st = world
    registry(home, [{"scope": "user", "version": "0.1.3", "installPath": "/x"}])
    code, out, _ = run("--apply", fail=True)
    assert code == L.INCOMPLETE and (pb / "bin" / "pitboard").exists()
    assert ("  kept: plugin windstorm-pit-board@thewindstorm (user scope) (run yourself: claude plugin uninstall "
            "windstorm-pit-board@thewindstorm --scope user)") in census(out)
    assert "stand-in: failed on purpose" in out


def test_G18_3_a_project_scope_install_is_kept_and_named(world):
    home, pb, st = world
    registry(home, [{"scope": "project", "version": "0.1.3", "installPath": "/x", "projectPath": "/repo"}])
    calls = []
    code, out, _ = run("--apply", calls=calls)
    assert code == 0 and calls == []
    assert any(r.startswith("  kept: plugin windstorm-pit-board@thewindstorm in /repo (project scope)") and
               "cd /repo && claude plugin uninstall" in r for r in census(out))


# ---------------------------------------------------------------- folders, and the old spelling

STAND_IN = r'''#!/usr/bin/env python3
import json, os, sys
with open(os.environ["STAND_IN_LOG"], "a") as f:
    f.write(" ".join(sys.argv[1:]) + " in " + os.getcwd() + "\n")
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
def folder(world, tmp_path, monkeypatch):
    home, pb, st = world
    lane = tmp_path / "work" / "lane"
    (lane / ".claude").mkdir(parents=True)
    (lane / ".claude" / "settings.local.json").write_text('{"model": "y"}\n')
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "claude").write_text(STAND_IN)
    (bindir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}/usr/bin:/bin")
    monkeypatch.setenv("STAND_IN_LOG", str(tmp_path / "calls.log"))
    from pitboard import folder as F
    monkeypatch.setattr(F, "sessions_in", lambda folder, ps_lines=None, cwd_of=None: [])
    assert run_cli("setup", "--folder", str(lane), "--apply")[0] == 0
    return lane, tmp_path / "calls.log"


def test_G18_3_uninstall_finds_each_folder_and_puts_it_back(world, folder):
    home, pb, st = world
    lane, log = folder
    assert str(lane) in json.loads((pb / "setup-record.json").read_text())["folders"]
    code, out, _ = run_cli("uninstall", "--apply")
    assert code == 0, out
    assert (lane / ".claude" / "settings.local.json").read_text() == '{"model": "y"}\n'
    assert not (lane / ".claude" / L.FOLDER_RECORD).exists() and st.read_text() == MINE_TEXT
    assert f"plugin uninstall windstorm-pit-board@thewindstorm --scope local in {lane}" in log.read_text()


def test_G18_3_the_old_spelling_says_so_and_does_the_same(world, folder):
    lane, log = folder
    code, out, err = run_cli("setup", "--folder", str(lane), "--undo")
    assert code == 0 and err.startswith("pitboard: `setup --folder DIR --undo` is the old spelling of `pitboard "
                                        "uninstall --folder DIR --apply`")
    assert (lane / ".claude" / "settings.local.json").read_text() == '{"model": "y"}\n'
    assert "census:" in out and f"Pit Board is off in {lane}." in out


def test_G18_3_folder_alone_leaves_the_rest(world, folder):
    home, pb, st = world
    lane, _ = folder
    code, out, _ = run_cli("uninstall", "--folder", str(lane), "--apply")
    assert code == 0 and (pb / "bin" / "pitboard").exists() and st.read_text() != MINE_TEXT


# ---------------------------------------------------------------- the stable copy alone (point 9)

def _scrubbed(home):
    """A clean environment: no PITBOARD_HOME, no `claude` on the PATH. A shifted-clock run (the family's rule 25)
    hands on its two variables, so the programs started here read the shifted clock too."""
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
    env.update({k: os.environ[k] for k in ("LD_PRELOAD", "SHIFT_SECONDS") if k in os.environ})
    return env


def _launch(home, script, *args, stdin=""):
    env = _scrubbed(home)
    return subprocess.run([sys.executable, "-I", str(script), *args], input=stdin, capture_output=True, text=True,
                          env=env, timeout=60)


def _orphan(home):
    """Claude Code's own uninstall: the registry has no row; the version folder stays, marked .orphaned_at,
    and its code (if it ran) would leave a mark."""
    registry(home, None)
    ver = home / ".claude" / "plugins" / "cache" / "thewindstorm" / "windstorm-pit-board" / "0.1.3"
    shutil.copytree(os.path.join(ROOT, "pitboard"), ver / "pitboard", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(os.path.join(ROOT, "bin"), ver / "bin")
    shutil.copytree(os.path.join(ROOT, "hooks"), ver / "hooks")
    (ver / ".orphaned_at").write_text("1763856000000")
    cli_py = ver / "pitboard" / "cli.py"
    cli_py.write_text(f"open({str(home / 'ORPHAN-RAN')!r}, 'a').write('x')\n" + cli_py.read_text())
    return ver


def test_G18_3_the_stable_copy_alone_takes_itself_off(world):
    home, pb, st = world
    _orphan(home)
    r = _launch(home, pb / "pitboard" / "launch.py", "uninstall", "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    assert st.read_text() == MINE_TEXT and sorted(os.listdir(pb)) == ["lanes", "logs"]
    assert not (home / "ORPHAN-RAN").exists()                            # no orphaned code ran
    assert "  kept: 2 asks (1 open) in 1 lane log, and the log of what Pit Board did in ~/.pitboard (yours)" in r.stdout
    assert r.stdout.splitlines()[-1] == "They are yours, to keep or delete after you look at them."


def test_G18_3_the_stable_copy_alone_with_no_plugin_folder_and_no_registry_row(world):
    home, pb, st = world
    registry(home, None)
    assert not (home / ".claude" / "plugins" / "cache").exists()
    r = _launch(home, pb / "pitboard" / "launch.py", "uninstall", "--apply")
    assert r.returncode == 0 and st.read_text() == MINE_TEXT and not (pb / "bin").exists(), r.stdout + r.stderr


def test_G18_3_after_claude_codes_own_uninstall_status_hook_and_commands(world):
    home, pb, st = world
    ver = _orphan(home)
    line = "Pit Board was removed by Claude Code · run ~/.pitboard/bin/pitboard uninstall"
    r = _launch(home, pb / "pitboard" / "launch.py", "status", stdin='{"session_id": "s"}')
    assert (r.returncode, r.stdout, r.stderr) == (0, line, "")
    log = pb / "logs" / "pitboard.log"
    n = len(log.read_text().splitlines())
    for launcher in (pb / "pitboard" / "launch.py", ver / "pitboard" / "launch.py"):   # a session still running
        r = _launch(home, launcher, "hook", "session-start", stdin='{"session_id": "s", "cwd": "/"}')
        assert (r.returncode, r.stdout, r.stderr) == (0, "", ""), r
    new = log.read_text().splitlines()[n:]
    assert len(new) == 2 and all(ln.endswith(" session-start - Pit Board was removed by Claude Code; nothing done")
                                 for ln in new)
    r = _launch(home, pb / "pitboard" / "launch.py", "board")
    assert r.returncode == 1 and r.stderr == "pitboard: no installed version found\n" + line + "\n"
    assert not (home / "ORPHAN-RAN").exists()


def test_G18_3_an_unreadable_registry_is_not_removed(world):
    home, pb, st = world
    registry(home, None).write_text("{not json")
    r = _launch(home, pb / "pitboard" / "launch.py", "status", stdin='{"session_id": "s"}')
    assert r.returncode == 0 and "removed" not in r.stdout


def test_G18_3_setup_copies_leave_and_writes_the_record(world):
    home, pb, st = world
    assert (pb / "pitboard" / "leave.py").read_bytes() == open(os.path.join(ROOT, "pitboard", "leave.py"), "rb").read()
    rec = json.loads((pb / "setup-record.json").read_text())
    (entry,) = rec["files"]
    assert entry["path"] == str(st) and entry["before"] == MINE_TEXT and entry["before_mode"] == 0o644
    assert entry["after_sha256"] == hashlib.sha256(st.read_bytes()).hexdigest()
    assert run_cli("setup", "--minimal", "--apply")[0] == 0                # again: the first before stays
    assert json.loads((pb / "setup-record.json").read_text())["files"][0]["before"] == MINE_TEXT


def test_G18_3_the_census_counts_only_the_backups_setups_record_lists(world):
    """P29 (plan 1.32): other tools name their backups the same way; only the record says which are setup's."""
    home, pb, st = world
    mine = [n for n in os.listdir(home / ".claude") if n.startswith("settings.json.bak-")]
    assert json.loads((pb / "setup-record.json").read_text())["files"][0]["backups"] == mine and len(mine) == 1
    (home / ".claude" / "settings.json.bak-20261114-statusline").write_text("{}")     # a stranger's, same form
    (home / ".claude" / "settings.json.bak-20991231-235959").write_text("{}")         # even setup's own stamp form
    code, out, _ = run("--apply")
    assert code == 0, out
    rows = census(out)
    assert [r for r in rows if ".bak-" in r] == [
        f"  kept: 1 backup setup made of ~/.claude/settings.json (yours: ~/.claude/{mine[0]})"]
    assert (home / ".claude" / "settings.json.bak-20261114-statusline").exists()       # never touched


def test_G18_3_a_home_from_before_the_list_says_it_cannot_tell_which_backups_are_setups(world):
    """P29: set up before the record listed backups (0.1.2 wrote no record): no count is called setup's."""
    home, pb, st = world
    os.remove(pb / "setup-record.json")
    (home / ".claude" / "settings.json.bak-20261114-statusline").write_text("{}")
    code, out, _ = run("--apply")
    assert code == 0, out
    assert [r for r in census(out) if ".bak-" in r] == [
        "  kept: 2 files named ~/.claude/settings.json.bak-* (setup kept no list of its backups then, so Pit Board "
        "cannot tell which are its own; yours to keep or delete)"]


def test_G18_3_an_unreadable_record_gives_no_backup_count(world):
    """P29 and rule 6: a record that could not be read is not "no backups": it says so and counts nothing."""
    home, pb, st = world
    (pb / "setup-record.json").write_text("[1, 2]")
    code, out, _ = run("--apply")
    rows = census(out)
    assert not [r for r in rows if ".bak-" in r]
    assert any(r.startswith("  kept: the setup record in ~/.pitboard") for r in rows), rows


def test_G18_3_leave_is_standard_library_only_and_imports_no_pit_board_code():
    with open(os.path.join(ROOT, "pitboard", "leave.py"), encoding="utf-8") as f:
        tree_ = ast.parse(f.read())
    names = set()
    for node in ast.walk(tree_):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import"
            names.add(node.module.split(".")[0])
    assert names <= {"fcntl", "hashlib", "json", "os", "re", "shlex", "shutil", "subprocess", "sys", "textwrap", "time"}, names


def test_G18_3_json_is_one_object(world):
    code, out, _ = run("--json")
    d = json.loads(out)
    assert code == 0 and set(d) == {"ok", "exit", "message", "ids", "asks", "data"} and d["data"]["applied"] is False
    assert {"state": "would go", "what": "~/.pitboard/bin", "why": ""} in d["data"]["census"]


def _by_hand_lines():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        text = f.read()
    part = text[text.index("**A home set up before 0.1.3**"):]
    return part[part.index("```\n") + 4:part.index("\n```", part.index("```\n") + 4)].splitlines()


@pytest.mark.parametrize("own", ["echo mine", None])
def test_G18_3_the_readmes_by_hand_lines_for_a_home_from_before_0_1_3(world, own):
    home, pb, st = world
    if own is None:                                         # no status line of the person's own before setup
        shutil.rmtree(pb)
        st.write_text('{"model": "x"}')
        assert run_cli("setup", "--minimal", "--apply")[0] == 0
        (pb / "lanes").mkdir(exist_ok=True)
        (pb / "lanes" / "api.jsonl").write_text('{"type": "asked", "uid": "u1"}\n')
    os.remove(pb / "pitboard" / "leave.py")                 # what a 0.1.2 home has: no leave.py, no record
    os.remove(pb / "setup-record.json")
    lines = _by_hand_lines()
    assert len(lines) == 1                                  # the maintainer's ruling: no removal line on the front page
    assert not re.search(r"\b(rm|rmdir|find|unlink|shutil|remove|delete)\b", lines[0]), lines[0]
    home_before = tree(pb)
    r = subprocess.run(["bash", "-c", lines[0]], env=_scrubbed(home), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    want = dict(MINE) if own else {"model": "x"}
    assert json.loads(st.read_text()) == want
    assert tree(pb) == home_before                          # Pit Board's home is the person's to delete
    r = subprocess.run(["bash", "-c", lines[0]], env=_scrubbed(home),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and json.loads(st.read_text()) == want                 # run again: nothing changes


def test_G18_3_an_orphaned_folders_own_launcher_never_runs_its_leave(world):
    home, pb, st = world
    ver = _orphan(home)
    (ver / "pitboard" / "leave.py").write_text(f"open({str(home / 'ORPHAN-RAN')!r}, 'a').write('x')\n"
                                               "def main(argv):\n    return 0\n")
    r = _launch(home, ver / "pitboard" / "launch.py", "uninstall", "--apply")        # the home's leave.py runs
    assert r.returncode == 0 and st.read_text() == MINE_TEXT and not (home / "ORPHAN-RAN").exists(), r.stderr
    r = _launch(home, ver / "pitboard" / "launch.py", "uninstall")                    # no home copy left: none runs
    assert r.returncode == 1 and not (home / "ORPHAN-RAN").exists()
    assert r.stderr == "pitboard: no installed version found\nPit Board was removed by Claude Code\n"   # no copy to name


def test_G18_3_the_kept_line_names_a_command_that_runs_here(world):
    home, pb, st = world
    plan = run()[1].splitlines()[-2]
    assert plan.endswith("They are yours. When you are sure, you can delete them yourself, at your own terminal: "
                         "~/.pitboard/bin/pitboard uninstall --apply --delete-asks-and-log")                         # the copy is there while it is a plan
    r = subprocess.run(["bash", "-c", plan.split("at your own terminal: ", 1)[1]], env=_scrubbed(home),
                       capture_output=True, text=True, timeout=60)         # run exactly as printed, here with no
    assert r.returncode == 2 and (pb / "bin" / "pitboard").exists()      # terminal: it refuses, changes nothing
    assert "--delete-asks-and-log runs only at your own terminal" in r.stderr
    out = run("--apply")[1]
    assert not DELETE.search(out) and (pb / "lanes").exists()   # P48: no line is a recursive delete
    assert out.splitlines()[-1] == "They are yours, to keep or delete after you look at them."


def test_G18_3_a_path_with_a_space_is_quoted(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert L._shell(str(tmp_path / ".pitboard")) == "~/.pitboard"
    assert L._shell(str(tmp_path / "my home")) == "'" + str(tmp_path / "my home") + "'"


def test_G18_3_byte_for_byte_is_said_only_while_nothing_else_wrote_the_file(world):
    home, pb, st = world
    registry(home, [{"scope": "user", "version": "0.1.3", "installPath": "/x"}])
    code, out, _ = run("--apply")
    assert code == 0 and ("  gone: status line setting in ~/.claude/settings.json (put back byte for byte; then Claude "
                          "Code's own uninstall changed its entries in that file)") in census(out)


# ---------------------------------------------------------------- P30: what Claude Code's own uninstall did

def _as_seen_on_2_1_331(home, catalog_listed=True):
    """The home as Claude Code 2.1.331 left it in the rule 23 round: its uninstall dropped the registry row, rewrote
    ~/.claude.json and kept the version folder marked .orphaned_at; the catalog stayed listed."""
    ver = home / ".claude" / "plugins" / "cache" / "thewindstorm" / "windstorm-pit-board" / "0.1.3"
    (ver / "bin").mkdir(parents=True)
    (home / ".claude.json").write_text('{"numStartups": 1}\n')
    known = home / ".claude" / "plugins" / "known_marketplaces.json"
    known.write_text(json.dumps({"thewindstorm": {"source": {"source": "github"}}} if catalog_listed else {}))

    def effect(args):
        registry(home, None)
        (home / ".claude.json").write_text('{"numStartups": 1, "changed": true}\n')
        (ver / ".orphaned_at").write_text("1763952000000")
    return ver, effect


P30_FILES = ("  kept: Claude Code's own files: ~/.claude/plugins/installed_plugins.json, ~/.claude.json (changed by "
             "Claude Code's own uninstall, which Pit Board ran; they are Claude Code's)")
P30_FOLDER = ("  kept: ~/.claude/plugins/cache/thewindstorm/windstorm-pit-board/0.1.3 (Pit Board's code, a version folder "
              "Claude Code keeps in its plugin cache after its own uninstall (it marked it .orphaned_at); Claude Code's to "
              "clean up, so Pit Board leaves it)")
P30_CATALOG = ("  kept: the plugin catalog thewindstorm in Claude Code's list (other plugins install and update from it; "
               "removing it with `claude plugin marketplace remove thewindstorm` also uninstalls every plugin installed "
               "from that catalog, so Pit Board leaves it)")


def test_G18_3_the_census_names_what_claude_codes_own_uninstall_changed_and_kept(world):
    """P30: each line is read after the call, never assumed: the files it changed, the version folder it kept (with
    its mark), and the catalog, with what its removal does to every other plugin from it. Pit Board removes none."""
    home, pb, st = world
    registry(home, [{"scope": "user", "version": "0.1.3", "installPath": "/x"}])
    ver, effect = _as_seen_on_2_1_331(home)
    code, out, _ = run("--apply", effect=effect)
    rows = census(out)
    assert code == 0 and P30_FILES in rows and P30_FOLDER in rows and P30_CATALOG in rows, rows
    assert rows.index(P30_FILES) > rows.index("  gone: plugin windstorm-pit-board@thewindstorm (user scope)")
    assert ver.is_dir() and (home / ".claude" / "plugins" / "known_marketplaces.json").exists()


def test_G18_3_the_census_claims_only_what_it_read(world):
    """Nothing changed, no mark, the catalog gone: no line says otherwise. The plan, before any call, says none."""
    home, pb, st = world
    registry(home, [{"scope": "user", "version": "0.1.3", "installPath": "/x"}])
    ver, _ = _as_seen_on_2_1_331(home, catalog_listed=False)
    assert [r for r in census(run()[1]) if "Claude Code's own" in r or "catalog" in r] == []
    rows = census(run("--apply")[1])
    assert not [r for r in rows if "Claude Code's own files" in r or "catalog" in r], rows
    assert P30_FOLDER.replace(" (it marked it .orphaned_at)", "") in rows


@NOT_ROOT
def test_G18_3_an_unreadable_catalog_list_is_said_not_guessed(world):
    home, pb, st = world
    registry(home, [{"scope": "user", "version": "0.1.3", "installPath": "/x"}])
    ver, effect = _as_seen_on_2_1_331(home)
    known = home / ".claude" / "plugins" / "known_marketplaces.json"
    os.chmod(known, 0)
    try:
        rows = census(run("--apply", effect=effect)[1])
    finally:
        os.chmod(known, 0o600)
    assert ("  kept: the plugin catalog thewindstorm (~/.claude/plugins/known_marketplaces.json could not be read "
            "(PermissionError), so Pit Board cannot say whether Claude Code still lists it)") in rows
    assert P30_CATALOG not in rows


# ---------------------------------------------------------------- P40: a home that is not Pit Board's alone

def _put(folder, rels):
    for rel in rels:
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_text("mine\n")
    return {rel: "mine\n" for rel in rels}


def _still(folder, mine):
    return {rel: (folder / rel).read_text() for rel in mine if (folder / rel).exists()} == mine


@pytest.mark.parametrize("where", ["your home folder", "a folder with your things", "the folder option"])
def test_G18_1_setup_refuses_a_home_that_is_not_pit_boards_alone(tmp_path, monkeypatch, where):
    """P40: before any write, plan or --apply, --minimal or --folder."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text(MINE_TEXT)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    if where == "your home folder":
        target, mine = home, _put(home, ["Documents/letter.txt"])
    else:
        target = tmp_path / "mine"
        mine = _put(target, ["notes.txt", "bin/my-script.sh"])
    monkeypatch.setenv("PITBOARD_HOME", str(target))
    before = tree(tmp_path)
    argv = [["setup", "--minimal"], ["setup", "--minimal", "--apply"]]
    if where == "the folder option":
        (tmp_path / "proj").mkdir()
        before = tree(tmp_path)
        argv = [["setup", "--folder", str(tmp_path / "proj"), "--apply"]]
    for a in argv:
        code, out, err = run_cli(*a)
        assert code == 2 and "setup refused" in err and "not a folder for Pit Board alone" in err, (code, out, err)
        assert ("it is your home folder" if where == "your home folder" else "notes.txt") in err
        assert err.rstrip().endswith("Nothing changed.")
    assert tree(tmp_path) == before and _still(target, mine)


def test_G18_3_a_file_of_yours_put_in_the_home_after_setup_never_stops_the_leave(world):
    """P40 and rule 8: the default home gained a file of the person's after setup. Uninstall still takes Pit Board off:
    the status line is theirs again, what carries Pit Board's mark or setup's record is gone, Pit Board's folders that
    hold only its own files are gone; the person's file stays, named, with no command offered; exit 0."""
    home, pb, st = world
    mine = _put(pb, ["notes.txt"])
    code, out, _ = run("--apply")
    rows = census(out)
    assert code == 0, out
    assert st.read_text() == MINE_TEXT                                            # the status line is theirs again
    for gone in ("bin", "pitboard", "statusline.sh", "config.json", "state"):
        assert not (pb / gone).exists(), gone
    assert _still(pb, mine) and "  kept: ~/.pitboard/notes.txt (not made by Pit Board; yours)" in rows
    assert (pb / "lanes" / "api.jsonl").exists() and (pb / "logs" / "pitboard.log").exists()
    assert out.splitlines()[-1] == ("Pit Board is off this computer. What it left in ~/.pitboard, and why, is named "
                                    "above; it is yours, to keep or delete after you look at it.")
    assert "rm -r" not in out and "--delete-asks-and-log" not in out


def test_G18_3_a_file_of_yours_in_pit_boards_own_folder_stays_with_its_folder(world):
    """Inside a folder of Pit Board's own name only what Pit Board wrote goes: bin/pitboard carries its mark and goes;
    the person's script beside it stays, and so does the folder, named with the reason."""
    home, pb, st = world
    mine = _put(pb, ["bin/my-script.sh", "state/my-state"])
    code, out, _ = run("--apply")
    rows = census(out)
    assert code == 0 and _still(pb, mine), out
    assert not (pb / "bin" / "pitboard").exists() and not (pb / "pitboard").exists()
    assert ("  kept: ~/.pitboard/bin (Pit Board's, left because bin/my-script.sh in it is not; yours to delete after "
            "looking inside)") in rows
    assert sorted(p.name for p in (pb / "state").iterdir()) == ["my-state"]      # Pit Board's own state files went


def test_G18_3_pit_board_in_your_home_folder_takes_only_what_carries_its_mark_or_record(world, monkeypatch):
    """PITBOARD_HOME set to the person's home folder (setup refuses that now; a home from before 0.1.3 may be so):
    only marked and recorded files go; nothing else in the home folder is touched, and the home folder stays."""
    home, pb, st = world
    shutil.rmtree(pb)                                       # a home set up in the home folder, before 0.1.3's refusal
    st.write_text(MINE_TEXT)                                # the person's own settings, as before any setup
    monkeypatch.setenv("PITBOARD_HOME", str(home))
    monkeypatch.setattr(L, "is_home_folder", lambda h: False)
    monkeypatch.setattr(L, "foreign", lambda h: [])
    assert run_cli("setup", "--minimal", "--apply")[0] == 0
    (home / "lanes").mkdir(exist_ok=True)
    (home / "lanes" / "api.jsonl").write_text('{"type": "asked", "uid": "u1"}\n')
    monkeypatch.undo()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("PITBOARD_HOME", str(home))
    mine = _put(home, ["Documents/letter.txt", "state/my-state", "logs/my.log"])
    code, out, _ = run("--apply")
    assert code == 0, out
    assert st.read_text() == MINE_TEXT and _still(home, mine)
    assert not (home / "bin" / "pitboard").exists() and not (home / "statusline.sh").exists()
    assert not (home / "pitboard" / "launch.py").exists() and not (home / "config.json").exists()   # mark, record
    assert (home / "state").is_dir() and (home / "lanes" / "api.jsonl").exists() and home.is_dir()
    assert "rm -r" not in out


def test_G18_3_asks_and_log_are_never_deleted_from_a_home_that_is_not_pit_boards_alone(world):
    home, pb, st = world
    mine = _put(pb, ["logs/my.log", "notes.txt"])
    code, out, _ = run("--apply", "--delete-asks-and-log", stdin=Tty("2\n"), stdout=Tty())
    assert _still(pb, mine) and (pb / "lanes" / "api.jsonl").exists() and st.read_text() == MINE_TEXT, out
    assert "This deletes" not in out and "rm -r" not in out
    assert ("  kept: your asks and the log of what Pit Board did, in ~/.pitboard (you asked to delete them, but it holds "
            "logs/my.log, notes.txt, which Pit Board did not make; so nothing there was deleted. Yours to delete after you "
            "look inside)") in census(out), census(out)


def test_G18_3_a_home_of_pit_boards_alone_still_goes_whole_file_by_file(world):
    """The copies a long-lived home holds (.prev, a bytecode folder) are Pit Board's; the home goes but the asks."""
    home, pb, st = world
    (pb / "pitboard" / "launch.py.prev").write_text((pb / "pitboard" / "launch.py").read_text())
    (pb / "pitboard" / "__pycache__").mkdir()
    (pb / "pitboard" / "__pycache__" / "leave.cpython-312.pyc").write_bytes(b"\0")
    code, out, _ = run("--apply")
    assert code == 0 and sorted(os.listdir(pb)) == ["lanes", "logs"], out
    assert out.splitlines()[-1] == "They are yours, to keep or delete after you look at them."


def test_G18_3_the_kept_line_names_only_what_is_there_and_an_empty_logs_folder_goes(world):
    """P43 (seen on a stock machine 2026-11-24): a home whose hooks never wrote a log line has an empty logs/. Before,
    the census said it kept "the log of what Pit Board did" when there was none, and the empty logs/ stayed."""
    home, pb, st = world
    for n in os.listdir(pb / "logs"):
        os.remove(pb / "logs" / n)
    code, out, _ = run()
    assert code == 0 and (pb / "logs").is_dir()                                   # the plan changes nothing
    assert "  would go: ~/.pitboard/logs" in census(out)
    code, out, _ = run("--apply")
    rows = census(out)
    assert code == 0 and not (pb / "logs").exists() and "  gone: ~/.pitboard/logs" in rows
    assert "  kept: 2 asks (1 open) in 1 lane log in ~/.pitboard (yours)" in rows
    assert not [r for r in rows if "the log of what Pit Board did" in r]


def _no_claude_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("PITBOARD_HOME", raising=False)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    assert run_cli("setup", "--minimal", "--apply")[0] == 0
    assert (home / ".claude" / "settings.json").exists()
    return home


def test_G18_3_a_folder_setup_made_for_the_settings_file_goes_when_empty(tmp_path, monkeypatch):
    """P46 (seen on a real Mac, 2026-11-24, an account with no Claude Code): setup made ~/.claude for the settings
    file; uninstall removed the file ("there was none before") and left the empty ~/.claude, named nowhere. Empty
    lanes/ and logs/ go too. P48: then setup's record goes last, and the home with it."""
    home = _no_claude_home(tmp_path, monkeypatch)
    code, out, _ = run()
    assert code == 0 and "  would go: ~/.claude (made by setup when there was none; empty)" in census(out)
    assert (home / ".claude").is_dir()
    code, out, _ = run("--apply")
    rows = census(out)
    assert code == 0 and "  gone: ~/.claude (made by setup when there was none; empty)" in rows
    assert not (home / ".claude").exists()
    assert os.listdir(home) == [] and out.splitlines()[-1] == "  gone: ~/.pitboard (Pit Board's home, empty)"
    assert not [r for r in rows if "asks" in r or "the log of" in r]


def test_G18_3_a_folder_setup_made_that_holds_the_persons_file_is_named_and_kept(tmp_path, monkeypatch):
    home = _no_claude_home(tmp_path, monkeypatch)
    (home / ".claude" / "mine.txt").write_text("mine")
    code, out, _ = run()
    assert "  kept: ~/.claude (made by setup when there was none; left because mine.txt in it is not Pit Board's; yours)" in census(out)
    code, out, _ = run("--apply")
    assert code == 0 and (home / ".claude" / "mine.txt").read_text() == "mine"
    assert "  kept: ~/.claude (made by setup when there was none; left because mine.txt in it is not Pit Board's; yours)" in census(out)


def listing(path):
    """Every entry under path, folders too: kind, mode, and the bytes of a file (the family's whole-home listing)."""
    out = {}
    for d, dirs, files in os.walk(path):
        for n in dirs + files:
            p = os.path.join(d, n)
            st = os.lstat(p)
            body = None
            if os.path.isfile(p) and not os.path.islink(p):
                with open(p, "rb") as f:
                    body = hashlib.sha256(f.read()).hexdigest()
            out[os.path.relpath(p, path)] = (oct(st.st_mode), body, os.readlink(p) if os.path.islink(p) else None)
    return out


def test_G18_3_P48_the_leave_leaves_the_home_as_found_with_no_step_by_hand(tmp_path, monkeypatch):
    """P48 (the family's rule 8, read on a real Mac 2026-11-24): the leave kept setup's record and then printed
    `rm -r ~/.pitboard` for the person to run, so the account was as found only after that line was run by hand.
    Setup's record is Pit Board's: it goes last, then the empty home. The listing after equals the listing before
    setup, and no line printed is a delete."""
    home = tmp_path / "home"
    (home / "Documents").mkdir(parents=True)
    (home / "Documents" / "letter.txt").write_text("mine\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("PITBOARD_HOME", raising=False)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    before = listing(home)
    assert run_cli("setup", "--minimal", "--apply")[0] == 0 and (home / ".pitboard" / "setup-record.json").exists()
    code, plan, _ = run()
    assert code == 0 and "  would go: ~/.pitboard/setup-record.json (setup's record; last, once every step above was done)" in census(plan)
    assert "  would go: ~/.pitboard (Pit Board's home, empty by then)" in census(plan) and listing(home) != before
    code, out, _ = run("--apply")
    assert code == 0, out
    assert listing(home) == before                                     # identical, no clean-up by hand
    assert not DELETE.search(out) and "They are yours" not in out
    assert census(out)[-2:] == ["  gone: ~/.pitboard/setup-record.json (setup's record; last, once every step above was done)",
                                "  gone: ~/.pitboard (Pit Board's home, empty)"]
    code, again, _ = run("--apply")
    assert code == 0 and again == "nothing of Pit Board is here\n" and listing(home) == before   # a second run


def test_G18_3_P48_with_the_persons_own_settings_every_difference_is_a_named_line(world):
    """P48: with a settings file of the person's, the one difference left is setup's backup of it, kept and named."""
    home, pb, st = world
    for n in os.listdir(pb / "lanes"):
        os.remove(pb / "lanes" / n)
    os.remove(pb / "lanes.json") if (pb / "lanes.json").exists() else None
    shutil.rmtree(pb / "logs")
    shutil.rmtree(pb / "lanes")
    code, out, _ = run("--apply")
    assert code == 0 and not pb.exists() and st.read_text() == MINE_TEXT, out
    baks = sorted(n for n in os.listdir(home / ".claude") if ".bak-" in n)
    assert baks and f"  kept: 1 backup setup made of ~/.claude/settings.json (yours: ~/.claude/{baks[0]})" in census(out)
    assert not DELETE.search(out)


def test_G18_3_P48_a_leave_that_did_not_finish_keeps_setups_record(world):
    """P48: the record goes only once every step before it was done; else the next run needs it."""
    home, pb, st = world
    registry(home, [{"scope": "user", "installPath": str(home), "version": "0.1.2"}])
    code, out, _ = run("--apply", fail=True)                           # Claude Code's own uninstall failed
    assert code == 11 and (pb / "setup-record.json").exists() and "setup-record.json" not in "".join(
        r for r in census(out) if r.startswith("  gone"))
    assert not DELETE.search(out)


def test_G18_3_P48_a_home_not_pit_boards_alone_keeps_setups_record_named(world):
    """P48 and rule 23: in a home holding another's things, the record stays and is named, with no command."""
    home, pb, st = world
    (pb / "notes.txt").write_text("not Pit Board's\n")
    code, out, _ = run("--apply")
    assert code == 0 and (pb / "setup-record.json").exists() and (pb / "notes.txt").exists()
    assert any("setup's record (setup-record.json)" in r for r in census(out)) and not DELETE.search(out)


@pytest.mark.parametrize("there_before", [False, True])
def test_G18_3_P48_a_home_a_setting_names_goes_only_when_setup_made_it(tmp_path, monkeypatch, there_before):
    """P48 and the family's rule 23 (A FOLDER A SETTING CAN NAME IS NOT OURS UNTIL WE MADE IT): with PITBOARD_HOME
    naming a folder, setup records that it made it; the leave removes that folder only then. A folder the person made
    before setup stays, empty, and is named as theirs."""
    home, pbh = tmp_path / "home", tmp_path / "their-place" / "pb"
    home.mkdir()
    (tmp_path / "their-place").mkdir()
    if there_before:
        pbh.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PITBOARD_HOME", str(pbh))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    before = listing(tmp_path)
    assert run_cli("setup", "--minimal", "--apply")[0] == 0
    assert (json.loads((pbh / "setup-record.json").read_text()).get("made_home") is True) is (not there_before)
    code, out, _ = run("--apply")
    assert code == 0 and not DELETE.search(out), out
    if there_before:
        assert pbh.is_dir() and os.listdir(pbh) == []
        assert census(out)[-1] == f"  kept: {pbh} (empty; it was there before setup made anything in it, so it is yours)"
    else:
        assert listing(tmp_path) == before and census(out)[-1] == f"  gone: {pbh} (Pit Board's home, empty)"


@pytest.mark.parametrize("mode", [0o600, 0o644])
def test_G18_3_P50_the_readmes_by_hand_line_runs_as_printed_and_keeps_the_mode(tmp_path, monkeypatch, mode):
    """P50 (seen with a real Claude Code on a real Mac, 2026-11-24): the README's by-hand line for a home set up before
    0.1.3 wrote the settings file anew with the default mode, so a settings file of mode 600 (the shape of a real
    account: a status line of four keys, ten keys in all) came back 644. Run exactly as printed it now puts the person's
    own status line back with its other keys, changes no other key, and keeps the file's mode."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    st = home / ".claude" / "settings.json"
    own = {"type": "command", "command": str(home / ".claude" / "my-status.sh"), "padding": 0, "refreshInterval": 5}
    mine = {"env": {"MY_SETTING": "1"}, "model": "opus", "statusLine": own, "theme": "dark"}
    st.write_text(json.dumps(mine, indent=2) + "\n")
    os.chmod(st, mode)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("PITBOARD_HOME", raising=False)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    assert run_cli("setup", "--minimal", "--apply")[0] == 0
    os.chmod(st, mode)                                         # as the file was left: 600 by setup, or the person's
    line, = _by_hand_lines()
    r = subprocess.run(["bash", "-c", line], env=_scrubbed(home), capture_output=True, text=True, timeout=60,
                       cwd=str(home), stdin=subprocess.DEVNULL)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == "", r
    now = json.loads(st.read_text())
    assert now["statusLine"] == own and {k: v for k, v in now.items() if k != "statusLine"} == {
        k: v for k, v in mine.items() if k != "statusLine"}
    assert stat.S_IMODE(os.stat(st).st_mode) == mode, oct(os.stat(st).st_mode)
    assert not (home / ".claude" / "settings.json.tmp").exists()
    (home / ".claude" / "settings.json.tmp").write_text("left by something else")       # a leftover: never written
    before = st.read_bytes()                                                               # through, never widened
    assert run_cli("setup", "--minimal", "--apply")[0] == 0
    os.chmod(st, mode)
    r = subprocess.run(["bash", "-c", line], env=_scrubbed(home), capture_output=True, text=True, timeout=60,
                       cwd=str(home), stdin=subprocess.DEVNULL)
    assert r.returncode != 0 and (home / ".claude" / "settings.json.tmp").read_text() == "left by something else"
    assert json.loads(st.read_text())["statusLine"]["command"].endswith("statusline.sh") and before != st.read_bytes()


def test_G18_3_P58_with_no_claude_on_the_path_the_census_names_a_step_the_person_can_take(world):
    """P58, its 0.1.3 half (seen on a real Mac's test account: the stop said "run yourself: claude plugin uninstall",
    which a person who took Claude Code off first cannot do). With no `claude`, the line says so, says the status line
    is back, says Pit Board's files stay, and names the step there is."""
    home, pb, st = world
    registry(home, [{"scope": "user", "version": "0.1.3", "installPath": "/x"}])

    def no_claude(args, **kw):
        raise FileNotFoundError("claude")
    out, err = io.StringIO(), io.StringIO()
    code = L.main(["--apply"], stdin=io.StringIO(""), stdout=out, stderr=err, run=no_claude)
    rows = census(out.getvalue())
    assert code == L.INCOMPLETE and st.read_text() == MINE_TEXT                       # the status line is back
    assert "  gone: status line setting in ~/.claude/settings.json (put back byte for byte)" in rows
    line = [r for r in rows if r.startswith("  kept: plugin windstorm-pit-board@thewindstorm (user scope)")]
    assert line == ["  kept: plugin windstorm-pit-board@thewindstorm (user scope) (`claude` was not found on the "
                    "PATH, so Claude Code's own entry for the plugin stays; your status line is already back, and Pit "
                    "Board's files stay where the line below says. If Claude Code is still on this account, put its "
                    "`claude` on the PATH and run ~/.pitboard/bin/pitboard uninstall --apply again. If Claude Code "
                    "is gone, nothing of Pit Board runs any more)"], rows
    assert "run yourself: claude plugin uninstall" not in out.getvalue()
    assert any(r.startswith("  kept: Pit Board's files in ~/.pitboard (a step above was not finished") for r in rows)
    assert not DELETE.search(out.getvalue())                                         # P48: no printed delete


def test_G18_3_P54_the_status_lines_kept_files_go_with_the_rest(world):
    """P54: `status` keeps one file per session in state/ (and, if it was stopped mid-write, one temporary file of its
    process). Both are Pit Board's own names, so the leave takes them with the rest and the home ends as before."""
    home, pb, st = world
    (pb / "state").mkdir(exist_ok=True)
    sid = "491fc210-0721-4fac-a44f-4ddaab42d465"
    (pb / "state" / f"{sid}.seg").write_text(f"{cli.SEG_MARK} 0.1.3 9999999999 1 0 7\n\n\n")
    (pb / "state" / f"{sid}.seg.4242.tmp").write_text("cut short")
    code, out, _ = run("--apply")
    assert code == 0, out
    assert sorted(os.listdir(pb)) == ["lanes", "logs"]


# ---------------------------------------------------------------- the way back in (the family's rule 8)

def _no_claude(args, **kw):
    raise FileNotFoundError(args[0])                                     # `claude` is on no PATH: the leave is cut


@pytest.mark.parametrize("leaving", ["keep", "delete", "cut"])
def test_G18_3_the_way_back_in_setup_leave_setup_again_and_an_ask_is_added_and_shown(world, leaving):
    """The family's rule 8 (THE WAY BACK IN IS WALKED TOO): setup, an ask, a leave in each form (keeping the asks,
    deleting them at the person's own terminal, and one cut half way because `claude` cannot be run), then setup
    again: it answers 0, and the commands after it work: the kept ask is shown where it was kept, a new ask is added
    and shown with it."""
    home, pb, st = world
    assert run_cli("add", "--lane", "circle", "--title", "first?", "--suggested", "yes")[0] == 0
    if leaving == "keep":
        code, out, _ = run("--apply")
        assert code == 0 and set(os.listdir(pb)) <= {"lanes", "lanes.json", "logs"}, out   # only the person's things
    elif leaving == "delete":
        _, ask, _ = run("--apply", "--delete-asks-and-log", stdin=Tty("\n"), stdout=Tty())   # changes nothing: the count
        n = re.search(r"Type (\d+) to do both", ask).group(1)
        code, out, _ = run("--apply", "--delete-asks-and-log", stdin=Tty(n + "\n"), stdout=Tty())
        assert code == 0 and not pb.exists(), out
    else:
        registry(home, [{"scope": "user", "installPath": str(home / "cache" / "x"), "version": "0.1.3"}])
        out, err = io.StringIO(), io.StringIO()
        code = L.main(["--apply"], stdin=io.StringIO(""), stdout=out, stderr=err, run=_no_claude)
        assert code == L.INCOMPLETE and "a step above was not finished" in out.getvalue(), out.getvalue()
        assert (pb / "setup-record.json").exists() and (pb / "statusline.sh").exists()   # kept for the next run
        assert st.read_text() == MINE_TEXT                                   # the person's status line is back
    code, out, err = run_cli("setup", "--minimal", "--apply")
    assert code == 0, out + err
    assert json.loads(st.read_text())["statusLine"]["command"] == str(pb / "statusline.sh")
    kept = 0 if leaving == "delete" else 1
    code, out, _ = run_cli("status", "--lane", "circle", "--plain")
    assert code == 0 and (out == "" if kept == 0 else out.startswith("🔴 RED 1 ask")), out
    code, out, _ = run_cli("add", "--lane", "circle", "--title", "second?", "--suggested", "yes")
    assert code == 0 and out.startswith(f"A{kept + 1} recorded"), out
    code, out, _ = run_cli("status", "--lane", "circle", "--plain")
    assert code == 0 and out.startswith(f"🔴 RED {kept + 1} ask"), out
    code, out, _ = run_cli("board", "--lane", "circle", "--plain")
    assert code == 0 and ("first?" in out) == bool(kept) and "second?" in out, out
