"""G18.3 `pitboard uninstall` (plan 1.28, P17): one way of leaving; what is the person's stays and is counted."""
import ast
import fcntl
import hashlib
import io
import json
import os
import shutil
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


def run(*argv, stdin=None, stdout=None, calls=None, fail=False):
    """leave.main with a stand-in for `claude`: records each call; fail=True answers exit 1."""
    out, err = stdout or io.StringIO(), io.StringIO()

    def fake(args, **kw):
        if calls is not None:
            calls.append((args, kw.get("cwd")))
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
    assert sorted(os.listdir(pb)) == ["lanes", "logs", "setup-record.json"]
    assert os.listdir(pb / "lanes") == ["api.jsonl"]                                  # its lock file went
    assert sorted(n for n in os.listdir(home / ".claude") if ".bak-" in n) == backups and backups   # yours
    rows = census(out)
    assert "  gone: status line setting in ~/.claude/settings.json (put back byte for byte)" in rows
    assert "  gone: ~/.pitboard/bin" in rows and "  gone: ~/.pitboard/statusline.sh" in rows
    assert f"  kept: 1 backup(s) setup made of ~/.claude/settings.json (yours: ~/.claude/settings.json.bak-*)" in rows
    assert out.splitlines()[-1] == ("kept: 2 asks (1 open) in 1 lane log, and the log of what Pit Board did, at "
                                    "~/.pitboard. They are yours; to delete them too: rm -r ~/.pitboard")


def test_G18_3_run_twice_says_nothing_of_pit_board_is_here(world):
    home, pb, st = world
    assert run("--apply")[0] == 0
    before = tree(home)
    code, out, _ = run("--apply")
    assert code == 0 and out.startswith("nothing of Pit Board is here\ncensus:\n") and tree(home) == before
    assert not [r for r in census(out) if r.startswith("  gone")]
    assert out.splitlines()[-1].startswith("kept: 2 asks (1 open) in 1 lane log")


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
    code, out, _ = run("--apply", "--delete-asks-and-log", stdin=Tty("1\n"), stdout=Tty())
    assert code == 0 and (pb / "lanes" / "api.jsonl").exists()           # 1 is not the count: nothing deleted
    assert "Type 2 to delete them" in out and "you did not type the count; nothing deleted" in out
    code, out, _ = run("--apply", "--delete-asks-and-log", stdin=Tty("2\n"), stdout=Tty())
    assert code == 0 and not pb.exists()
    assert "  gone: your asks and the log of what Pit Board did, in ~/.pitboard (you typed the count)" in census(out)
    assert not [r for r in census(out) if r.startswith("  kept: your asks")]


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
        "  gone: status line setting in ~/.claude/settings.json (put back byte for byte)")


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

def _launch(home, script, *args, stdin=""):
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
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
    assert st.read_text() == MINE_TEXT and sorted(os.listdir(pb)) == ["lanes", "logs", "setup-record.json"]
    assert not (home / "ORPHAN-RAN").exists()                            # no orphaned code ran
    assert r.stdout.splitlines()[-1].startswith("kept: 2 asks (1 open) in 1 lane log")


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
    assert names <= {"fcntl", "hashlib", "json", "os", "shlex", "shutil", "subprocess", "sys", "textwrap", "time"}, names


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
    assert len(lines) == 2
    for line in lines:
        r = subprocess.run(["bash", "-c", line], env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
    want = dict(MINE) if own else {"model": "x"}
    assert json.loads(st.read_text()) == want
    assert sorted(os.listdir(pb)) == ["lanes", "logs"]
    r = subprocess.run(["bash", "-c", lines[0]], env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
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
    assert plan.endswith("To delete them too, at your own terminal: ~/.pitboard/bin/pitboard uninstall --apply "
                         "--delete-asks-and-log")                         # the copy is there while it is a plan
    after = run("--apply")[1].splitlines()[-1]
    assert after.endswith("They are yours; to delete them too: rm -r ~/.pitboard") and (pb / "lanes").exists()
    r = subprocess.run(["bash", "-c", after.split("to delete them too: ", 1)[1]], env={"HOME": str(home),
                       "PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and not pb.exists()                         # run exactly as printed


def test_G18_3_a_path_with_a_space_is_quoted(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert L._shell(str(tmp_path / ".pitboard")) == "~/.pitboard"
    assert L._shell(str(tmp_path / "my home")) == "'" + str(tmp_path / "my home") + "'"
