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
    os.chmod(home / ".claude", 0o755)                 # P41: the fixture's own folder, not the runner's umask
    old = os.umask(os.umask(0) | 0o022)               # what the launcher does first (P41): these tests skip it
    yield home, pb
    os.umask(old)


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


def test_G2_1_setup_makes_the_home_700_under_a_loose_umask(world):
    """P34, the half that holds since the first release: a home that setup makes is 700, whatever the umask.
    The code folders under it are only the process's default mode."""
    home, pb = world
    old = os.umask(0o002)
    try:
        code, _, _ = run("setup", "--minimal", "--apply")
    finally:
        os.umask(old)
    assert code == 0
    assert stat.S_IMODE(pb.stat().st_mode) == 0o700
    assert {d: stat.S_IMODE((pb / d).stat().st_mode) for d in ("lanes", "state", "logs")} == dict.fromkeys(
        ("lanes", "state", "logs"), 0o700)
    assert stat.S_IMODE((pb / "config.json").stat().st_mode) == 0o600


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


@pytest.mark.parametrize("before, words", [
    (0o664, ["set statusLine.command to the wrapper (no status line before; backup kept)",
             "the file is 664 now and is written private (600); the backup keeps 664",
             "uninstall puts 664 back only when it puts the file back byte for byte"]),
    (0o600, ["set statusLine.command to the wrapper (no status line before; backup kept)"]),
    (None, ["set statusLine.command to the wrapper (no status line before; no settings file before)",
            "the file is made private (600); there is nothing to back up"]),
])
def test_G18_1_the_plan_says_what_happens_to_the_settings_files_mode(world, before, words):
    """P25: seen on two machines and a stock virtual machine, a settings file went from 664 to 600 and the plan said only
    that statusLine.command would be set. Now the plan says it first, whole (no line cut at the width), and a missing
    file is not said to be backed up."""
    home, pb = world
    p = home / ".claude" / "settings.json"
    if before is not None:
        settings(home, {"model": "x"})
        os.chmod(p, before)
    code, out, _ = run("setup", "--minimal")
    lines = [ln.strip() for ln in out.splitlines()]
    at = lines.index(words[0])
    assert code == 0 and lines[at:at + len(words)] == words, out     # whole lines: none cut at the width
    nxt = lines[at + len(words)] if at + len(words) < len(lines) else ""
    assert not nxt.startswith(("the file is", "uninstall puts")), out   # nothing more said for this item
    run("setup", "--minimal", "--apply")
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    baks = sorted((home / ".claude").glob("settings.json.bak-*"))
    assert [stat.S_IMODE(b.stat().st_mode) for b in baks] == ([] if before is None else [before])


def test_G2_nothing_pit_board_makes_is_writable_by_another_account_whatever_the_umask(tmp_path):
    """The family's rule 28 (seen 2026-11-23: a wrapper started a skill under umask 000). Pit Board started under umask
    000: setup twice, a session's hooks, one ask, the status line. Every entry it made is read back: none writable by
    group or others (bin/ and pitboard/ were 777 and state/*.activity 666 before). The second setup is not refused,
    nor is a third in a home an older start left with 777 folders (P40's guard counts names, never modes)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PITBOARD_MACHINE": "studio-1"}
    launcher = os.path.join(root, "bin", "pitboard")

    def go(*argv, stdin="", script=None):
        return subprocess.run(["sh", script or launcher, *argv], input=stdin, env=env, capture_output=True, text=True,
                              timeout=60, preexec_fn=lambda: os.umask(0))

    for n in (1, 2):
        r = go("setup", "--minimal", "--apply")
        assert r.returncode == 0 and "refused" not in r.stdout + r.stderr, (n, r.stdout, r.stderr)
    pb = home / ".pitboard"
    hook_in = json.dumps({"session_id": "s1", "cwd": str(tmp_path), "transcript_path": "", "source": "startup",
                          "prompt": "go on"})
    assert go("hook", "session-start", stdin=hook_in).returncode == 0
    r = go("add", "--lane", "umask", "--title", "Umask?", "--suggested", "yes")
    assert r.returncode == 0, r.stderr
    for ev in ("user-prompt-submit", "stop"):
        assert go("hook", ev, stdin=hook_in).returncode == 0
    subprocess.run([str(pb / "statusline.sh")], input=json.dumps({"session_id": "s1", "cwd": str(tmp_path)}), env=env,
                   capture_output=True, text=True, timeout=60, preexec_fn=lambda: os.umask(0))
    made = [p for p in home.rglob("*") if p != home / ".claude"]
    assert len(made) > 15 and (pb / "state").is_dir() and any((pb / "state").glob("*.activity"))
    loose = sorted(f"{stat.S_IMODE(p.lstat().st_mode):o} {p.relative_to(home)}" for p in made
                   if stat.S_IMODE(p.lstat().st_mode) & 0o022)
    assert loose == []
    for d in [pb] + [p for p in pb.rglob("*") if p.is_dir()]:
        os.chmod(d, 0o777)                                       # what an older start under umask 000 left
    r = go("setup", "--minimal", "--apply")
    assert r.returncode == 0 and "refused" not in r.stdout + r.stderr, (r.stdout, r.stderr)


def test_G2_a_private_file_is_opened_new_never_written_into_a_temp_file_left_before(world, monkeypatch):
    """P41 (the family's rule 28): a temp file an earlier run left (here 666, under both names Pit Board has used) is
    never written into: before, the lane map came out 666 that way and the settings file was written and then
    narrowed to 600. A backup is opened new at the mode the file had (664, P25) and never over an earlier backup."""
    from pitboard import leave, store
    home, pb = world
    pb.mkdir(mode=0o700)
    target = pb / "lanes.json"
    for leftover in (f"{target}.tmp", f"{target}.{os.getpid()}.tmp"):
        with open(leftover, "w") as f:
            f.write("old")
        os.chmod(leftover, 0o666)
    store.write_json_atomic(str(target), {"a": 1})
    assert stat.S_IMODE(target.stat().st_mode) == 0o600 and json.loads(target.read_text()) == {"a": 1}
    assert not os.path.exists(f"{target}.{os.getpid()}.tmp")
    with pytest.raises(FileExistsError):                          # write_new never writes over a file that is there
        leave.write_new(str(target), b"x", 0o600)
    assert json.loads(target.read_text()) == {"a": 1}
    p = settings(home, {"model": "x"}) and home / ".claude" / "settings.json"
    os.chmod(p, 0o664)
    left = home / ".claude" / f"settings.json.{os.getpid()}.tmp"
    left.write_text("old"); os.chmod(left, 0o666)
    code, _, _ = run("setup", "--minimal", "--apply")
    assert code == 0 and stat.S_IMODE(p.stat().st_mode) == 0o600 and not left.exists()
    baks = sorted((home / ".claude").glob("settings.json.bak-*"))
    assert [stat.S_IMODE(b.stat().st_mode) for b in baks] == [0o664] and json.loads(baks[0].read_text()) == {"model": "x"}
    earlier, stamp = baks[0].read_bytes(), baks[0].name.split(".bak-")[1]
    monkeypatch.setattr(S, "_stamp", lambda: stamp)              # a second write in the same second
    S.apply([S.Item("again", str(p), "set", b"{}\n", 0o600)])
    assert baks[0].read_bytes() == earlier                       # an earlier backup is never written over
    assert (home / ".claude" / f"settings.json.bak-{stamp}-2").exists()


@pytest.fixture
def short_tmp():
    """A short folder, so a plan line with a path is not cut at the CLI's width (pytest's own paths are long)."""
    import tempfile
    d = tempfile.mkdtemp(prefix="pb", dir="/tmp")
    yield __import__("pathlib").Path(d)
    for top, dirs, files in os.walk(d):
        for n in dirs:
            os.chmod(os.path.join(top, n), 0o700)
    shutil.rmtree(d)


def test_G2_setup_closes_its_own_and_names_the_folders_on_the_way(short_tmp):
    """P41 (the family's rule 28, a file is only as closed as the folders above it): a home as 0.1.2 left it under
    umask 000 (bin/ and pitboard/ 777, an activity file 666). The plan says it would close them and changes nothing;
    --apply closes them. ~/.claude above the settings file, and the folder above a home that is not the default, are
    the person's: named with the one command when another account can reach and write them, never changed, and
    `pitboard version` says it again while it stays open. Nothing of the person's changes."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    home = short_tmp / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / "mine.txt").write_text("mine")
    os.chmod(claude / "mine.txt", 0o666)
    os.chmod(claude, 0o777)                                      # any account can write it...
    os.chmod(home, 0o755)
    os.chmod(short_tmp, 0o755)                                   # ...and reach it
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PITBOARD_MACHINE": "studio-1"}

    def go(*argv, **extra):
        return subprocess.run(["sh", os.path.join(root, "bin", "pitboard"), *argv], env={**env, **extra},
                              capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)

    assert go("setup", "--minimal", "--apply").returncode == 0
    pb = home / ".pitboard"
    (pb / "state").mkdir(exist_ok=True)
    (pb / "state" / "s1.activity").write_text("idle 2026-11-24T00:00:00Z\n")
    for rel, m in (("bin", 0o777), ("pitboard", 0o777), ("state/s1.activity", 0o666)):
        os.chmod(pb / rel, m)                                    # what 0.1.2 left under umask 000

    def modes():
        return {str(p.relative_to(home)): stat.S_IMODE(p.lstat().st_mode) for p in [home] + list(home.rglob("*"))}

    before = modes()
    r = go("setup", "--minimal")
    assert r.returncode == 0 and modes() == before, r.stdout
    out = r.stdout
    assert "would close: group and other write taken off" in out
    assert "bin (777)" in out and "pitboard (777)" in out and "state/s1.activity (666)" in out
    assert "a folder on the way, not Pit Board's: " + str(claude) in out
    assert "777: any account can reach and write it; setup does not change it" in out and f"chmod go-w {claude}" in out
    r = go("setup", "--minimal", "--apply")
    assert r.returncode == 0 and "closed: group and other write taken off" in r.stdout, r.stdout
    after = modes()
    assert [k for k, m in after.items() if k.startswith(".pitboard") and m & 0o022] == []
    assert after[".claude"] == 0o777 and after[".claude/mine.txt"] == 0o666     # the person's: never changed
    assert after["."] == before["."]
    v = go("version").stdout.splitlines()
    at = v.index(f"open to other accounts: {claude} (777)")
    assert v[at + 1:at + 3] == ["  any account can reach and write it", f"  to close it: chmod go-w {claude}"]
    assert v[-1].startswith("status line runs")                           # P15: still the last line
    os.chmod(claude, 0o755)
    shared = short_tmp / "shared"
    shared.mkdir(mode=0o700)
    os.chmod(shared, 0o777)
    r = go("setup", "--minimal", PITBOARD_HOME=str(shared / "pb"))
    assert r.returncode == 0 and f"a folder on the way, not Pit Board's: {shared}" in r.stdout, r.stdout
    assert f"{claude}" not in r.stdout.split("a folder on the way")[-1]  # closed now: not named
    assert stat.S_IMODE(shared.stat().st_mode) == 0o777


def test_G2_a_folder_of_the_persons_is_named_only_when_another_account_can_reach_and_write_it(short_tmp, monkeypatch):
    """P41, the family's rule 28 (WHEN A PERSON'S FOLDER IS NAMED): a 775 folder in the person's own group with
    nobody else in it is the ordinary state on a Linux desktop and is not named; with a second member it is named
    when every folder above lets that member pass, and not when the home above is 700; a membership that cannot be
    read is said so."""
    home, pb = short_tmp / "home", short_tmp / "pb"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    os.chmod(short_tmp, 0o755)                                   # every folder above lets any account pass
    settings_path = str(claude / "settings.json")
    os.chmod(claude, 0o775)
    os.chmod(home, 0o755)
    gid = claude.stat().st_gid
    monkeypatch.setattr(S, "_other_members", lambda g, owner: set())
    assert str(claude) not in {w for w, _, _, _ in S.way_open(str(pb), settings_path)}     # a group of one
    monkeypatch.setattr(S, "_other_members", lambda g, owner: {4242} if g == gid else set())
    monkeypatch.setattr(S, "_groups", lambda uid: {gid})
    named = {w: why for w, _, why, _ in S.way_open(str(pb), settings_path)}
    assert named.get(str(claude)) == "account 4242 of its group can reach and write it"
    os.chmod(home, 0o700)                                        # a home at 700 keeps everyone out
    assert str(claude) not in {w for w, _, _, _ in S.way_open(str(pb), settings_path)}
    os.chmod(home, 0o755)
    monkeypatch.setattr(S, "_other_members", lambda g, owner: None)
    named = {w: why for w, _, why, _ in S.way_open(str(pb), settings_path)}
    assert named.get(str(claude)) == "its group's members could not be read"


def test_G2_an_account_is_its_number_not_its_name(short_tmp, monkeypatch):
    """The family's rule 28 (AN ACCOUNT IS ITS NUMBER, NOT ITS NAME): a second name with the person's own user number,
    in the folder's group, is the person, not another account: a group-writable folder under a passable home is not
    named. Seen on a fleet machine: two names with one user number, one primary group, one home."""
    import grp
    import pwd
    home, pb = short_tmp / "home", short_tmp / "pb"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    os.chmod(short_tmp, 0o755)
    os.chmod(home, 0o755)
    os.chmod(claude, 0o775)
    me, gid = os.getuid(), claude.stat().st_gid
    Pw = type("Pw", (), {})
    def pw(name, uid, g):
        e = Pw(); e.pw_name, e.pw_uid, e.pw_gid = name, uid, g; return e
    people = [pw("person", me, gid), pw("person-alias", me, gid)]
    monkeypatch.setattr(pwd, "getpwall", lambda: people)
    monkeypatch.setattr(pwd, "getpwnam", lambda n: next(p for p in people if p.pw_name == n))
    monkeypatch.setattr(grp, "getgrgid", lambda g: type("G", (), {"gr_mem": ["person-alias"], "gr_name": "person"})())
    settings_path = str(claude / "settings.json")
    assert S._other_members(gid, me) == set()
    assert str(claude) not in {w for w, _, _, _ in S.way_open(str(pb), settings_path)}
    people.append(pw("someone-else", me + 1, gid))                # control: a second NUMBER in the group is named
    monkeypatch.setattr(S, "_groups", lambda uid: {gid})
    assert str(claude) in {w for w, _, _, _ in S.way_open(str(pb), settings_path)}


def test_G2_a_folder_another_account_owns_on_the_way_is_named_with_no_command(short_tmp, monkeypatch):
    """P42 (the family's rule 28): a folder on the way that another account (not root) owns and can reach is named
    with who owns it and that only an administrator can hand it back, and with no chmod: the person cannot change it.
    Here the person is made a different number than the one that owns the folders."""
    home, pb = short_tmp / "home", short_tmp / "pb"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    for d in (short_tmp, home, claude):
        os.chmod(d, 0o755)
    owner = os.getuid()
    monkeypatch.setattr(S.os, "getuid", lambda: owner + 1)        # the person runs as another number
    out = S.way_open(str(pb), str(claude / "settings.json"))
    named = {w: (why, fix) for w, _, why, fix in out}
    who = S._name(owner)
    for d in (claude, home, short_tmp):
        assert named[str(d)] == (f"owned by account {who}; only an administrator can hand it back", None), named
    assert "/" not in named and "/tmp" not in named                     # root's: never named
    items = S.closing_items(str(pb), str(claude / "settings.json"))
    text = S.describe(items)
    assert "chmod" not in text and "only an administrator can hand it back" in text
    assert "access lists (ACLs) are not read" in text


def test_G2_a_folder_root_owns_that_another_account_can_write_is_named_as_roots_with_no_command(short_tmp, monkeypatch):
    """P42 (the family's rule 28, 12:03 AM ET clause): a folder on the way that is root's and that another account can
    write never falls into the person's branch: its line names root as the owner and gives no command. A sticky
    folder (as /tmp) is not named: no other account can remove or replace what the person owns in it."""
    home, pb = short_tmp / "home", short_tmp / "pb"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    for d in (short_tmp, home):
        os.chmod(d, 0o755)
    os.chmod(claude, 0o777)
    real = os.lstat

    def as_roots(p, *a, **k):
        st = real(p, *a, **k)
        if os.path.abspath(p) == str(claude):
            t = list(st)
            t[4] = 0                                             # st_uid: root
            return os.stat_result(t)
        return st
    monkeypatch.setattr(S.os, "lstat", as_roots)
    named = {w: (why, fix) for w, _, why, fix in S.way_open(str(pb), str(claude / "settings.json"))}
    assert named[str(claude)] == ("owned by root, and any account can reach and write it; only an administrator can "
                                  "close it", None)
    assert "chmod" not in S.describe(S.closing_items(str(pb), str(claude / "settings.json")))
    os.chmod(claude, 0o1777)
    assert str(claude) not in {w for w, _, _, _ in S.way_open(str(pb), str(claude / "settings.json"))}


def test_G2_an_account_with_the_macs_nobody_group_number_is_read_never_a_traceback(short_tmp, monkeypatch):
    """P44 (the family's rule 28, read on two Macs 2026-11-24): accounts there carry group 4294967294 ("nobody", -2
    without its sign) and Apple's Python 3.9 raises OverflowError from os.getgrouplist on it, while the signed number
    answers. The walk asks again signed; an account whose groups still cannot be read is said so, and the walk goes
    on. os.getgrouplist is stood in, as the Mac answers."""
    import pwd
    calls = []

    def mac_getgrouplist(name, gid):
        calls.append(gid)
        if gid > 2 ** 31 - 1:
            raise OverflowError("signed integer is greater than maximum")
        return [gid, 12]
    monkeypatch.setattr(S.os, "getgrouplist", mac_getgrouplist)
    e = type("Pw", (), {"pw_name": "macuser", "pw_uid": 501, "pw_gid": 4294967294})()
    monkeypatch.setattr(pwd, "getpwuid", lambda uid: e)
    assert S._groups(501) == {4294967294, 12} and calls == [4294967294, -2]
    monkeypatch.setattr(S.os, "getgrouplist", lambda n, g: (_ for _ in ()).throw(OverflowError("no")))
    assert S._groups(501) is None                                # unreadable: None, never a traceback
    home, pb = short_tmp / "home", short_tmp / "pb"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    for d in (short_tmp, home):
        os.chmod(d, 0o755)
    os.chmod(claude, 0o775)
    monkeypatch.setattr(S, "_other_members", lambda g, owner: {501})
    named = {w: why for w, _, why, _ in S.way_open(str(pb), str(claude / "settings.json"))}
    assert named[str(claude)] == "the groups of account macuser in its group could not be read"
