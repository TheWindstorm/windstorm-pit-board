"""P54: a status line redraw when nothing it shows could have changed starts no Python.

Seen on a real Mac: one redraw through the wrapper took 130 to 150 ms under Apple's python3, the person's own script
11 ms, and a person who refreshes every 5 s pays it in every session all the time. The wrapper now shows the segment
Pit Board kept for the session (state/<session id>.seg) when nothing it depends on changed, and starts only `cat`
(its input) and `date` (the clock) on that road; everything else runs Pit Board as before.

The inputs are Claude Code's own bytes (tests/fixtures/statusline, captured from Claude Code 2.1.331; only the
paths and one usage number were replaced). Every program the wrapper starts is counted through stand-ins first on
PATH, under dash, bash, and bash --posix (the Mac's /bin/sh is bash).
"""
import io
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone

import pytest

from pitboard import __version__, cli, contract as c, lane as L, render as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "statusline")
SID = "491fc210-0721-4fac-a44f-4ddaab42d465"            # the captured session's own id
COUNTED = ("cat", "date", "python3", "python", "sed", "awk", "grep", "head", "tail", "tr", "wc", "env", "stat",
           "touch", "mktemp", "sleep", "dirname", "sh", "bash", "dash", "timeout", "gtimeout", "printf", "test", "[", "expr")
SHELLS = [s for s in (["dash"], ["bash"], ["bash", "--posix"]) if shutil.which(s[0])]


def fixture(name):
    with open(os.path.join(FIX, name), "rb") as f:
        return f.read()


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    return cli.main(list(argv), stdout=out, stderr=err), out.getvalue(), err.getvalue()


@pytest.fixture
def world(tmp_path, monkeypatch):
    home, pb = tmp_path / "home", tmp_path / "pb"
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PITBOARD_HOME", str(pb))
    monkeypatch.setenv("PITBOARD_MACHINE", "studio-1")
    for k in ("PITBOARD_LANE", "CLAUDE_CODE_SESSION_ID", "NO_COLOR", "PITBOARD_LAUNCH_NS", "PITBOARD_WRAPPER_SID",
              "PITBOARD_WRAPPER_NAME"):
        monkeypatch.delenv(k, raising=False)
    old = os.umask(os.umask(0) | 0o022)
    assert run("setup", "--minimal", "--apply")[0] == 0
    v = home / ".claude" / "plugins" / "cache" / "thewindstorm" / "windstorm-pit-board" / __version__
    shutil.copytree(os.path.join(ROOT, "pitboard"), v / "pitboard", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(os.path.join(ROOT, "bin"), v / "bin")
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps(
        {"version": 2, "plugins": {"windstorm-pit-board@thewindstorm": [
            {"scope": "user", "installPath": str(v), "version": __version__}]}}))
    L.resolve(SID, "API Server")
    shims, log = tmp_path / "shims", tmp_path / "starts.log"
    shims.mkdir()
    for name in COUNTED:
        real = shutil.which(name)
        if real and name not in ("[", "test", "printf"):
            (shims / name).write_text(f'#!/bin/sh\necho {name} >> "{log}"\nexec "{real}" "$@"\n')
            os.chmod(shims / name, 0o755)
    yield {"home": home, "pb": pb, "shims": str(shims), "log": log, "tmp": tmp_path}
    os.umask(old)


def redraw(w, data, shell=("sh",), **env_more):
    """One redraw as Claude Code makes it: the wrapper started with the session's JSON on stdin. Returns (bytes printed,
    the programs it started, in order)."""
    if w["log"].exists():
        w["log"].unlink()
    env = {"HOME": str(w["home"]), "PATH": w["shims"], **env_more}
    sh = [shutil.which(shell[0]) or "/bin/sh", *shell[1:]]
    r = subprocess.run([*sh, str(w["pb"] / "statusline.sh")], input=data, capture_output=True, env=env, timeout=30)
    starts = w["log"].read_text().split() if w["log"].exists() else []
    return r.stdout, starts


def segfile(w):
    return w["pb"] / "state" / (SID + ".seg")


def add(title="Go?"):
    assert run("add", "--lane", "api-server", "--title", title, "--suggested", "yes")[0] == 0


def settle(w, data, shell=("sh",), **env):
    """The first redraws of a session: Pit Board runs, and when the session has a name it notes it in the lane map
    (a change it made itself), so the next one runs it once more. Then quiet. Returns what the quiet one printed."""
    _, s1 = redraw(w, data, shell, **env)
    assert "python3" in s1
    for _ in range(2):
        out, starts = redraw(w, data, shell, **env)
        if starts == ["cat", "date"]:
            return out
    raise AssertionError(f"never quiet: {starts}")


def quiet(starts):
    return [s for s in starts if s not in ("cat", "date")] == []


@pytest.mark.parametrize("shell", SHELLS, ids=" ".join)
@pytest.mark.parametrize("asks", [0, 1])
@pytest.mark.parametrize("inp", ["no-name.json", "name-1.json"])
def test_G10_5_P54_a_redraw_with_nothing_changed_starts_only_cat_and_date(world, shell, asks, inp):
    for _ in range(asks):
        add()
    data = fixture(inp)
    first, s1 = redraw(world, data, shell)
    assert "python3" in s1 and segfile(world).exists()                     # the first redraw runs Pit Board
    assert (b"1 ask" in first) == bool(asks)
    if inp != "no-name.json":                                              # it noted the name: the lane map changed
        assert "python3" in redraw(world, data, shell)[1]
    second, s2 = redraw(world, data, shell)
    assert second == first and s2 == ["cat", "date"], s2                   # every start counted: cat and date only
    t = time.perf_counter()
    redraw(world, data, shell)
    print(f"P54 no-change redraw under {' '.join(shell)}: {(time.perf_counter() - t) * 1000:.1f} ms")


@pytest.mark.parametrize("shell", SHELLS, ids=" ".join)
@pytest.mark.parametrize("missing", ["config.json", "lane log", "update"])
def test_G10_5_P54_an_input_that_is_not_there_is_not_a_change_under_any_shell(world, shell, missing):
    """Seen 2026-11-24: `[ file -nt missing ]` is false in dash and true in bash. Existence is tested by itself: an
    input missing when the file was kept and still missing is quiet; one that appears runs Pit Board."""
    p = {"config.json": world["pb"] / "config.json", "lane log": world["pb"] / "lanes" / "api-server.jsonl",
         "update": world["pb"] / "update"}[missing]
    if p.is_dir():
        shutil.rmtree(p)
    elif p.exists():
        p.unlink()
    data = fixture("no-name.json")
    redraw(world, data, shell)
    assert redraw(world, data, shell)[1] == ["cat", "date"]
    if missing == "lane log":
        add()
    elif missing == "update":
        p.mkdir()
    else:
        p.write_text("{}")
    out, starts = redraw(world, data, shell)
    assert "python3" in starts
    assert (b"1 ask" in out) == (missing == "lane log")
    assert redraw(world, data, shell)[1] == ["cat", "date"]


@pytest.mark.parametrize("change", ["ask added", "ask answered", "lane map", "config", "update folder",
                                    "plugin registry", "launcher copy", "NO_COLOR"])
def test_G10_5_P54_each_change_runs_pit_board_once_then_quiet_again(world, change):
    add()
    data = fixture("name-1.json")
    settle(world, data)
    time.sleep(0.01)
    env = {}
    if change == "ask added":
        add("Second?")
    elif change == "ask answered":
        assert run("answer", "A1", "--lane", "api-server", "--by", "operator", "--answer", "yes")[0] == 0
    elif change == "lane map":
        L.resolve("0f3a9c2e-1b2c-4d5e-8f90-123456789abc", "Other")
    elif change == "config":
        (world["pb"] / "config.json").write_text('{"escalate_after_hours": 1}')
    elif change == "update folder":
        (world["pb"] / "update").mkdir(exist_ok=True)
        os.utime(world["pb"] / "update")
    elif change == "plugin registry":
        reg = world["home"] / ".claude" / "plugins" / "installed_plugins.json"
        reg.write_text(reg.read_text())
    elif change == "launcher copy":
        p = world["pb"] / "pitboard" / "launch.py"
        p.write_bytes(p.read_bytes())
    else:
        env = {"NO_COLOR": "1"}
    out, starts = redraw(world, data, **env)
    assert "python3" in starts, change
    if change == "ask added":
        assert b"2 asks" in out
    if change == "ask answered":
        assert out == b""
    if change == "NO_COLOR":
        assert b"\x1b[" not in out and b"1 ask" in out
    assert quiet(redraw(world, data, **env)[1]), change


def test_G10_5_P54_an_input_of_the_same_time_as_the_file_counts_as_changed(world):
    data = fixture("no-name.json")
    redraw(world, data)
    st = os.stat(segfile(world))
    os.utime(world["pb"] / "lanes.json", ns=(st.st_mtime_ns, st.st_mtime_ns))
    assert "python3" in redraw(world, data)[1]


def test_G10_5_P54_an_ask_that_lands_between_the_read_and_the_write_is_never_hidden(world, monkeypatch):
    """The status command reads its inputs, an ask lands, then the file is written. The file carries the moment the
    launcher started, so the new ask's log is newer than it and the next redraw runs Pit Board."""
    from pitboard import store
    data = fixture("name-1.json")
    real = store.read_state

    def read_then_an_ask_lands(*a, **k):
        st = real(*a, **k)
        time.sleep(0.01)
        add("Landed meanwhile?")
        return st
    monkeypatch.setattr(store, "read_state", read_then_an_ask_lands)
    monkeypatch.setenv("PITBOARD_LAUNCH_NS", str(time.time_ns()))
    monkeypatch.setenv("PITBOARD_WRAPPER_SID", SID)
    monkeypatch.setenv("PITBOARD_WRAPPER_NAME", 'Pit \\"Bo\\\\ard\\" é·1')
    real_stdin = cli.sys.stdin
    cli.sys.stdin = io.StringIO(data.decode())
    try:
        out = io.StringIO()
        cli.main(["status"], stdout=out, stderr=io.StringIO())
    finally:
        cli.sys.stdin = real_stdin
    assert out.getvalue() == "" and segfile(world).exists()                  # it read nothing open
    monkeypatch.setattr(store, "read_state", real)
    shown, starts = redraw(world, data)
    assert "python3" in starts and b"1 ask" in shown


@pytest.mark.parametrize("spoil", ["garbage", "cut short", "unreadable", "written in the future", "past its time",
                                   "other session name", "one input line less"])
def test_G10_5_P54_a_file_that_cannot_be_trusted_runs_pit_board(world, spoil):
    add()
    data = fixture("name-1.json")
    good = settle(world, data)
    f = segfile(world)
    lines = f.read_bytes().split(b"\n")
    head = lines[0].split(b" ")
    if spoil == "garbage":
        f.write_bytes(b"\x00\xff not a segment file\n")
    elif spoil == "cut short":
        f.write_bytes(b"\n".join(lines[:2]))
    elif spoil == "unreadable":
        if os.geteuid() == 0:
            pytest.skip("root reads a 000 file")
        os.chmod(f, 0)
    elif spoil == "written in the future":                # the clock went back after it was written
        head[4] = str(int(time.time()) + 3600).encode()
        f.write_bytes(b"\n".join([b" ".join(head)] + lines[1:]))
    elif spoil == "past its time":
        head[3] = str(int(time.time()) - 1).encode()
        f.write_bytes(b"\n".join([b" ".join(head)] + lines[1:]))
    elif spoil == "other session name":
        lines[1] = b"Pit"
        f.write_bytes(b"\n".join(lines))
    else:
        f.write_bytes(b"\n".join(lines[:-2] + lines[-1:]))
    out, starts = redraw(world, data)
    assert "python3" in starts, spoil
    assert out == good                                                      # Pit Board's own answer, never nothing


def test_G10_5_P54_a_pit_board_that_fails_shows_nothing_of_its_own_and_keeps_no_file(world):
    s = world["home"] / ".claude" / "settings.json"
    d = json.loads(s.read_text())
    assert d["statusLine"]["command"] == str(world["pb"] / "statusline.sh")
    (world["pb"] / "bin" / "pitboard").write_text("#!/bin/sh\ncat >/dev/null\nexit 3\n")
    out, starts = redraw(world, fixture("name-1.json"))
    assert out == b"" and not segfile(world).exists()


def test_G10_5_P54_the_name_is_one_text_the_wrapper_cut_and_a_rename_after_an_escaped_quote_is_seen(world):
    """Claude Code sends the name JSON-escaped (captured: "Pit \\"Bo\\\\ard\\" é·1"). The wrapper cuts it up to its
    first quote not escaped and hands that text to Pit Board, which stores it as it came."""
    add()
    one, two = fixture("name-1.json"), fixture("name-2.json")
    settle(world, one)
    assert segfile(world).read_bytes().split(b"\n")[1] == 'Pit \\"Bo\\\\ard\\" é·1'.encode()
    assert L.read_map()[SID]["lane_name"] == 'Pit "Bo\\ard" é·1'
    out, starts = redraw(world, two)                                         # differs only after the quote
    assert "python3" in starts
    assert segfile(world).read_bytes().split(b"\n")[1] == 'Pit \\"Bo\\\\ard\\" é·2'.encode()
    assert redraw(world, two)[1] == ["cat", "date"]
    # G10.6 notes a name at most once a minute: the rename waits, and the kept segment ends when it is due
    seen_p = world["pb"] / "state" / "statusline-seen.json"
    seen = json.loads(seen_p.read_text())
    due = int(c.parse_ts(seen[SID]).timestamp()) + cli.STATUSLINE_SEEN_SECONDS
    lines = segfile(world).read_bytes().split(b"\n")
    head = lines[0].split(b" ")
    assert int(head[3]) <= due and L.read_map()[SID]["lane_name"] == 'Pit "Bo\\ard" é·1'
    seen[SID] = c.ts_of(datetime.now(timezone.utc) - timedelta(minutes=2))  # the minute has passed
    seen_p.write_text(json.dumps(seen))
    head[3] = str(int(time.time()) - 1).encode()
    segfile(world).write_bytes(b"\n".join([b" ".join(head)] + lines[1:]))
    assert "python3" in redraw(world, two)[1]
    assert L.read_map()[SID]["lane_name"] == 'Pit "Bo\\ard" é·2'


@pytest.mark.parametrize("key", ["session_name", "session_id"])
def test_G10_5_P54_a_key_given_twice_keeps_no_file_and_always_runs_pit_board(world, key):
    add()
    t = fixture("name-1.json").decode()
    twice = t.replace('"cwd":', f'"{key}":"{SID if key == "session_id" else "x"}","cwd":', 1).encode()
    _, s1 = redraw(world, twice)
    _, s2 = redraw(world, twice)
    assert "python3" in s1 and "python3" in s2 and not segfile(world).exists()


def test_G10_5_P54_the_file_is_private_holds_no_asks_words_and_never_outlives_its_version(world):
    add("Secret plan words?")
    data = fixture("no-name.json")
    redraw(world, data)
    f = segfile(world)
    assert os.stat(f).st_mode & 0o777 == 0o600
    raw = f.read_bytes()
    assert b"Secret" not in raw and b"plan words" not in raw and b"1 ask" in raw
    assert raw.split(b" ")[2] == __version__.encode()
    reg = world["home"] / ".claude" / "plugins" / "installed_plugins.json"   # an update rewrites the registry
    time.sleep(0.01)
    reg.write_text(reg.read_text())
    assert "python3" in redraw(world, data)[1]


def test_G10_5_P54_old_files_go_and_only_ours(world):
    """The folder does not grow without end: a file of another version, or older than a week, goes when Pit Board
    next keeps one; a file not of our name or first line, or one that cannot be read, stays."""
    state = world["pb"] / "state"
    week = time.time() - 8 * 86400
    other_version = state / "11111111-0000-4000-8000-000000000001.seg"
    other_version.write_text(f"{cli.SEG_MARK} 0.0.1 {R.SEGMENT_NEVER} 1 0 7\n\n\n")
    old_ours = state / "11111111-0000-4000-8000-000000000002.seg"
    old_ours.write_text(f"{cli.SEG_MARK} {__version__} {R.SEGMENT_NEVER} 1 0 7\n\n\n")
    os.utime(old_ours, (week, week))
    not_ours = state / "11111111-0000-4000-8000-000000000003.seg"
    not_ours.write_text("a person's own file\n")
    os.utime(not_ours, (week, week))
    other_name = state / "Notes.seg"
    other_name.write_text(f"{cli.SEG_MARK} 0.0.1\n")
    unreadable = state / "11111111-0000-4000-8000-000000000004.seg"
    unreadable.write_text(f"{cli.SEG_MARK} 0.0.1\n")
    os.chmod(unreadable, 0)
    redraw(world, fixture("no-name.json"))
    left = sorted(p.name for p in state.iterdir() if p.name.endswith(".seg"))
    assert left == sorted([not_ours.name, other_name.name, SID + ".seg"]
                          + ([unreadable.name] if os.geteuid() != 0 else []))
    os.chmod(unreadable, 0o600) if unreadable.exists() else None


NOW = datetime(2026, 11, 24, 7, 0, 0, tzinfo=timezone.utc)


def _ask(n, asked, **kw):
    a = {"uid": f"{n:032x}", "ask": f"A{n}", "status": "open", "kind": "question", "severity": "can-wait",
         "deadline": None, "asked_at": c.ts_of(asked)}
    a.update(kw)
    return a


@pytest.mark.parametrize("asks", [
    [],
    [(0.2, {})],
    [(59.5, {})],
    [(150, {})],
    [(47 * 60 + 59.9, {})],
    [(49 * 60, {})],
    [(5, {}), (23 * 60 + 58, {})],                                     # a can-wait ask about to turn red
    [(5, {"severity": "blocking"})],
    [(5, {"deadline": 24 * 60 + 3})],                                   # a deadline about to come within a day
    [(5, {"kind": "hand"}), (30, {"deadline": 25 * 60})],
])
def test_G10_5_P54_the_segment_is_the_same_text_until_the_time_kept(asks):
    st = {"asks": [_ask(i, NOW - timedelta(minutes=m),
                        **({"deadline": c.ts_of(NOW + timedelta(minutes=kw["deadline"]))} if "deadline" in kw else
                           {k: v for k, v in kw.items()}))
                   for i, (m, kw) in enumerate(asks, 1)]}
    until = R.segment_until(st, NOW)
    seg = R.status_segment(st, NOW)
    if not asks:
        assert until == R.SEGMENT_NEVER and seg == ""
        return
    end = datetime.fromtimestamp(until, timezone.utc)
    assert end > NOW - timedelta(seconds=1)
    t = NOW
    while t < end:
        assert R.status_segment(st, t) == seg, t
        t += max(timedelta(seconds=1), (end - NOW) / 200)
    later = datetime.fromtimestamp(until + 1, timezone.utc)
    assert R.status_segment(st, later) != seg or R.segment_until(st, later) > until    # the time was not too early


SHELL_OWN = {"SHLVL", "_", "PWD", "OLDPWD"}               # what a shell sets for itself, with or without Pit Board


@pytest.mark.parametrize("shell", SHELLS, ids=" ".join)
@pytest.mark.parametrize("asks", [0, 1])
def test_G10_5_P54_rule2_the_persons_status_script_gets_the_environment_and_input_it_gets_without_pit_board(
        world, shell, asks):
    """Family rule 2 (A PERSON'S MACHINE IS FULL WHERE A STOCK ONE IS EMPTY), part 2 for the wrapper: the person's own
    status line command is run with the environment Claude Code gave the wrapper, nothing added and nothing taken
    (the wrapper's own names go only to Pit Board's part, after the person's line has run), and with the same bytes
    on stdin (P53). Lived-in: a token and tool settings exported, a value with a newline and one not ASCII."""
    for _ in range(asks):
        add()
    s = world["home"] / ".claude" / "settings.json"
    own = ("python3 -I -c 'import json,os,sys; b=sys.stdin.buffer.read(); "
           "print(json.dumps({\"env\": dict(os.environ), \"n\": len(b)}), end=\"\")'")
    d = json.loads(s.read_text())
    d["statusLine"]["command"] = own
    s.write_text(json.dumps(d))
    assert run("setup", "--minimal", "--apply")[0] == 0
    lived = {"GH_TOKEN": "ghp_short", "GIT_CONFIG_GLOBAL": str(world["tmp"] / "gitconfig"), "EDITOR": "vim",
             "LANG": "en_US.UTF-8", "MY_NOTE": "line one\nline two", "MY_NAME": "Zoë", "NO_COLOR": "1"}
    env = {"HOME": str(world["home"]), "PATH": os.environ["PATH"], **lived}
    data = fixture("name-1.json")
    direct = subprocess.run(["bash", "-c", own], input=data, capture_output=True, env=env, timeout=30).stdout
    for _ in range(3):                                               # Pit Board run, then the quiet road
        r = subprocess.run([shutil.which(shell[0]), *shell[1:], str(world["pb"] / "statusline.sh")], input=data,
                           capture_output=True, env=env, timeout=30).stdout
        text = r.decode()
        assert (" ask · oldest " in text) == bool(asks)                      # Pit Board's segment, then the person's
        got = json.loads(text[text.index("{"):])
        want = json.loads(direct)
        assert got["n"] == want["n"] == len(data)
        strip = lambda e: {k: v for k, v in e.items() if k not in SHELL_OWN}   # noqa: E731
        assert strip(got["env"]) == strip(want["env"])
        assert not [k for k in got["env"] if k.startswith("PITBOARD_")]
