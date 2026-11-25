"""P75 (G1.1): an event ends at a line feed only.

Python's splitlines() also breaks at U+2028, U+2029, U+0085 (NEL), VT, FF and FS, GS, RS. The writer left the first
three raw inside strings, so an older reader cut such an event into pieces that are not JSON and skipped them. Here
every one of those characters is planted in every text field of every event type that takes text, and every road
that reads a lane is read: once with the cache as the write left it, once with the state file gone. Also: a cache
an older copy built over a log holding a cut event, and a log holding two asks under one ID, which only an older
copy can have written (it gave out a lost ask's number again).
"""
import io
import itertools
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from pitboard import cli, contract as c, leave, lane as L, store as s

SID = "00000000-0000-4000-8000-000000000075"
KEY = "api-server"                  # the lane key of the session name "API Server"
# every character str.splitlines() ends a line at; "\n" and "\r" are written escaped by json.dumps
BREAKS = [" ", " ", "\u0085", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\r", "\n", "\r\n"]
RAW_BEFORE = (" ", " ", "\u0085")   # the three the old writer left raw


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("PITBOARD_HOME", str(tmp_path / "pb"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PITBOARD_MACHINE", "studio-1")
    monkeypatch.setenv("PITBOARD_TZ", "America/New_York")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(tmp_path / "env.sh"))
    for k in ("PITBOARD_LANE", "CLAUDE_CODE_SESSION_ID", "TMUX_PANE", "NO_COLOR", "COLUMNS", "PITBOARD_HUB_URL"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path


def run(*argv, stdin=None):
    out, err = io.StringIO(), io.StringIO()
    real = cli.sys.stdin
    cli.sys.stdin = io.StringIO(stdin or "")
    try:
        code = cli.main(list(argv), stdout=out, stderr=err)
    finally:
        cli.sys.stdin = real
    return code, out.getvalue() + err.getvalue()


def ok(*argv):
    code, text = run(*argv, "--lane", KEY)
    assert code == 0, (argv, text)
    return text


def js(*argv):
    code, text = run(*argv, "--lane", KEY, "--json")
    return json.loads(text)


def log_bytes():
    with open(s.log_path(KEY), "rb") as f:
        return f.read()


def state_gone():
    os.remove(s.state_path(KEY))


def reminder(home):
    t = home / "t.jsonl"
    t.write_text(json.dumps({"type": "custom-title", "customTitle": "API Server", "sessionId": SID}) + "\n")
    obj = {"session_id": SID, "hook_event_name": "SessionStart", "source": "startup", "cwd": str(home),
           "transcript_path": str(t), "session_title": "API Server"}
    code, text = run("hook", "session-start", stdin=json.dumps(obj))
    assert code == 0, text
    return json.loads(text)["hookSpecificOutput"]["additionalContext"]


# ---------------------------------------------------------------- every field, every road

def tch(ch):
    """A title is one line (G1.3): where `ch` holds a line feed, the title gets a space and every other field `ch`."""
    return " " if "\n" in ch else ch


def world(ch):
    """Every text field of every event type that takes text holds `ch`. (A deadline is a stored time, not text.)"""
    t = tch(ch)
    ok("add", "--title", f"t{t}MT1", "--suggested", f"s{ch}MS1", "--why", f"w{ch}MW1", "--detail", f"d{ch}MD1")
    ok("add", "--kind", "hand", "--title", f"h{t}MT2", "--step", f"p{ch}MP2", "--step", "plain")
    ok("update", "A2", "--detail", f"ud{ch}MUD2", "--step", f"q{ch}MQ2", "--suggested", f"us{ch}MUS2",
       "--why", f"uw{ch}MUW2", "--title", f"ut{t}MT2")
    ok("add", "--title", "three MT3", "--suggested", "y")
    ok("answer", "A3", "--by", "operator", "--answer", f"a{ch}MA3")
    ok("add", "--title", "four MT4", "--suggested", "y")
    ok("done", "A4", "--note", f"n{ch}MN4")
    ok("add", "--title", "five MT5", "--suggested", "y")
    ok("withdraw", "A5", "--reason", f"r{ch}MR5")
    ok("add", "--title", "six MT6", "--suggested", "y")
    ok("done", "A6")
    ok("reopen", "A6", "--reason", f"o{ch}MO6")
    ok("add", "--title", "seven MT7", "--suggested", "y")


EVENTS = 13
WANT = {
    "A1": {"status": "open", "title": "t{}MT1", "suggested": "s{}MS1", "why": "w{}MW1", "detail": "d{}MD1"},
    "A2": {"status": "open", "title": "ut{}MT2", "detail": "ud{}MUD2", "steps": ["q{}MQ2"], "suggested": "us{}MUS2",
           "why": "uw{}MUW2"},
    "A3": {"status": "answered", "answer": "a{}MA3"},
    "A4": {"status": "done", "done_note": "n{}MN4"},
    "A5": {"status": "withdrawn", "withdrawn_reason": "r{}MR5"},
    "A6": {"status": "open"},
    "A7": {"status": "open", "title": "seven MT7"},
}
OPEN = ("A1", "A2", "A6", "A7")


def want(ch, ask_id):
    def one(k, x):
        return x.format(tch(ch) if k == "title" else ch)
    return {k: ([one(k, x) for x in v] if isinstance(v, list) else one(k, v)) for k, v in WANT[ask_id].items()}


def read_every_road(home, ch):
    every = js("list", "--all")["asks"]
    assert sorted(a["ask"] for a in every) == sorted(WANT), "list --all: an ask is missing or doubled"
    by = {a["ask"]: a for a in every}
    for i in WANT:
        assert {k: by[i][k] for k in want(ch, i)} == want(ch, i), f"list --all: {i}"
    assert sorted(a["ask"] for a in js("list")["asks"]) == sorted(OPEN), "list"
    board = ok("board", "--plain")
    assert f"{len(OPEN)} open" in board and all(f"MT{i[1]}" in board for i in OPEN), board
    history = ok("board", "--all", "--plain")
    assert all(f"MT{n}" in history for n in range(1, 8)), history
    for i in WANT:
        shown = js("show", i)
        assert shown["ok"] and len(shown["asks"]) == 1, (i, shown)
        assert {k: shown["asks"][0][k] for k in want(ch, i)} == want(ch, i), f"show {i}"
    reopened = [e for e in js("show", "A6")["data"]["events"] if e["type"] == "reopened"]
    assert [e["data"]["reason"] for e in reopened] == [f"o{ch}MO6"]
    exported = [json.loads(ln) for ln in ok("export").split("\n") if ln.strip()]
    assert len([e for e in exported if e["lane"] == KEY]) == EVENTS, "export"
    code, seg = run("status", "--lane", KEY)
    assert code == 0 and f"{len(OPEN)} asks" in seg, seg
    told = reminder(home)
    assert all(f"MT{i[1]}" in told for i in OPEN) and "MT4" not in told, told


@pytest.mark.parametrize("ch", BREAKS, ids=[f"U+{ord(x[0]):04X}" + ("+LF" if len(x) > 1 else "") for x in BREAKS])
def test_G1_1_P75_an_event_ends_at_a_line_feed_only(home, ch):
    world(ch)
    raw = log_bytes()
    assert raw.count(b"\n") == EVENTS
    read_every_road(home, ch)                      # the cache as the writes left it
    state_gone()
    read_every_road(home, ch)                      # rebuilt from the log
    assert js("show", "A3")["asks"][0]["status"] == "answered"   # an answer holding one stays an answer
    ok("add", "--title", "eight MT8", "--suggested", "y")
    assert js("show", "A8")["ok"] and len(js("list", "--all")["asks"]) == 8   # never a number given out again


@pytest.mark.parametrize("ch", RAW_BEFORE, ids=["U+2028", "U+2029", "U+0085"])
def test_G1_1_P75_the_writer_stores_them_as_backslash_u_so_any_line_reader_sees_one_event(home, ch):
    world(ch)
    raw = log_bytes()
    assert ch.encode("utf-8") not in raw and f"\\u{ord(ch):04x}".encode() in raw
    text = raw.decode("utf-8")
    assert len(text.splitlines()) == len(text.split("\n")) - 1 == EVENTS    # an older copy's reader too
    assert all(json.loads(ln) for ln in text.splitlines())
    ev = c.make_event("asked", uid=c.new_id(), ask="A1", lane="x", lane_name="x", machine="m", session_id=None,
                      by="agent", data={"kind": "question", "severity": "blocking", "title": ch * 5,
                                        "suggested": "y", "source": "agent"})
    assert json.loads(c.serialize(ev))["data"]["title"] == ch * 5          # read back whole


# ---------------------------------------------------------------- a cache an older copy built

_TICK = itertools.count(1)


def old_line(**data):
    """One asked event as the release head's writer wrote it: U+2028 raw inside the title. Each planted event is
    a millisecond after the last (asked order is (ts, event_id)), all before the commands' own events."""
    ts = c.ts_of(datetime.now(timezone.utc) - timedelta(seconds=60) + timedelta(milliseconds=next(_TICK)))
    ev = c.make_event("asked", uid=c.new_id(), ask=data.pop("ask"), lane=KEY, lane_name=KEY, machine="studio-1",
                      session_id=None, by="agent", ts=ts,
                      data=dict({"kind": "question", "severity": "blocking", "suggested": "y", "source": "agent"},
                                **data))
    return (json.dumps(c.prepare(ev), ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def older_cache_over_a_cut_event():
    """The log holds a cut event (as an older reader saw it) and the cache an older copy wrote: it matches the
    log's size, has no reader mark and no doubled list, and does not hold the cut ask."""
    with open(s.log_path(KEY), "ab") as f:
        f.write(old_line(ask="A2", title="two MLOST"))
    st = s.read_json(s.state_path(KEY))
    st.pop("reader", None), st.pop("doubled", None)
    st["log_bytes"] = os.path.getsize(s.log_path(KEY))
    s.write_json_atomic(s.state_path(KEY), st)


def test_G1_1_P75_a_cache_an_older_copy_built_is_rebuilt_at_the_first_read(home):
    ok("add", "--title", "one MPLAIN", "--suggested", "y")
    older_cache_over_a_cut_event()
    board = ok("board", "--plain")
    assert "MLOST" in board and "2 open" in board, board
    assert s.read_json(s.state_path(KEY))["reader"] == s.READER
    assert "MLOST" in reminder(home)


def test_G1_1_P75_an_older_cache_then_an_answer_on_a_closed_id_keeps_the_lost_ask(home):
    ok("add", "--title", "one MPLAIN", "--suggested", "y")
    ok("done", "A1")
    older_cache_over_a_cut_event()
    code, text = run("answer", "A1", "--answer", "go", "--lane", KEY)
    assert code == 5 and "done" in text, text
    board = ok("board", "--plain")
    assert "MLOST" in board and "1 open" in board, board
    ok("add", "--title", "three MNEXT", "--suggested", "y")
    assert [a["ask"] for a in js("list", "--all")["asks"]] == ["A1", "A2", "A3"]


# ---------------------------------------------------------------- two asks under one ID

def doubled_log():
    """An older copy's log after it lost A2, rebuilt and gave A2 out again (both written whole here)."""
    s.ensure_home()
    lines = [old_line(ask="A1", title="one MPLAIN"), old_line(ask="A2", title="two MFIRST"),
             old_line(ask="A2", title="three MLATER")]
    with open(s.log_path(KEY), "ab") as f:
        f.write(b"".join(lines))
    uids = [json.loads(x)["uid"] for x in lines]
    return uids[1], uids[2]


def state_of(mode):
    if mode == "cache":
        s.rebuild_state(KEY)
    elif os.path.exists(s.state_path(KEY)):
        state_gone()


BY_ID = [("answer", "A2", "--answer", "go"), ("ok", "A2"), ("no", "A2"), ("done", "A2"),
         ("withdraw", "A2", "--reason", "moot"), ("update", "A2", "--why", "w")]


@pytest.mark.parametrize("mode", ("cache", "gone"))
@pytest.mark.parametrize("argv", BY_ID, ids=[a[0] for a in BY_ID])
def test_G1_1_P75_an_id_that_names_two_asks_acts_on_neither(home, mode, argv):
    first, later = doubled_log()
    state_of(mode)
    before = log_bytes()
    code, text = run(*argv, "--lane", KEY)
    assert code == 4 and log_bytes() == before, text
    assert first in text and later in text and "MFIRST" in text and "MLATER" in text, text
    assert "uid" in text and "nothing was written" in text, text


@pytest.mark.parametrize("mode", ("cache", "gone"))
def test_G1_1_P75_reopen_on_an_id_that_names_two_open_asks_writes_nothing(home, mode):
    first, later = doubled_log()
    state_of(mode)
    before = log_bytes()
    code, text = run("reopen", "A2", "--reason", "again", "--lane", KEY)
    assert code == 5 and log_bytes() == before and first in text and later in text, text


@pytest.mark.parametrize("mode", ("cache", "gone"))
def test_G1_1_P75_show_prints_every_ask_under_the_id(home, mode):
    first, later = doubled_log()
    state_of(mode)
    text = ok("show", "A2")
    assert text.startswith("A2 names 2 asks in this lane") and first in text and later in text, text
    shown = js("show", "A2")
    assert [a["uid"] for a in shown["asks"]] == [first, later]
    assert [a["uid"] for a in js("show", later)["asks"]] == [later]


BY_UID = [("answer", "--answer", "go", "answered"), ("done", "done"), ("withdraw", "--reason", "moot", "withdrawn"),
          ("update", "--why", "w", "open"), ("ok", "answered"), ("no", "answered")]


@pytest.mark.parametrize("mode", ("cache", "gone"))
@pytest.mark.parametrize("which", ("first", "later"))
@pytest.mark.parametrize("argv", BY_UID, ids=[a[0] for a in BY_UID])
def test_G1_1_P75_a_uid_names_one_ask_and_the_other_does_not_change(home, mode, which, argv):
    first, later = doubled_log()
    state_of(mode)
    target, other = (first, later) if which == "first" else (later, first)
    *flags, status = argv[1:]
    code, text = run(argv[0], target, *flags, "--lane", KEY)
    assert code == 0 and "A2" in text, text
    got = {a["uid"]: a for a in js("show", "A2")["asks"]}
    assert got[target]["status"] == status and got[target]["events"] == 2, got[target]
    assert got[other]["status"] == "open" and got[other]["events"] == 1
    ok("add", "--title", "next MNEXT", "--suggested", "y")
    assert js("show", "A3")["asks"][0]["title"] == "next MNEXT"


@pytest.mark.parametrize("mode", ("cache", "gone"))
def test_G1_1_P75_where_only_one_can_be_acted_on_the_line_names_it(home, mode):
    first, later = doubled_log()
    ok("done", first)                                       # by uid: the first is closed now
    state_of(mode)
    text = ok("answer", "A2", "--answer", "go")
    assert "MLATER" in text and later in text, text
    got = {a["uid"]: a for a in js("show", "A2")["asks"]}
    assert got[later]["status"] == "answered" and got[first]["status"] == "done"
    before = log_bytes()
    code, text = run("reopen", "A2", "--reason", "again", "--lane", KEY)   # reopen can act on both now
    assert code == 4 and log_bytes() == before and first in text and later in text, text


@pytest.mark.parametrize("mode", ("cache", "gone"))
def test_G1_1_P75_which_ask_an_id_means_never_depends_on_the_cache(home, mode):
    first, later = doubled_log()
    state_of(mode)
    shown = [a["uid"] for a in js("show", "A2")["asks"]]
    code, _ = run("answer", "A2", "--answer", "go", "--lane", KEY)
    assert shown == [first, later] and code == 4
    ok("add", "--title", "next MNEXT", "--suggested", "y")   # the next free number, never A2 or A1
    assert sorted(a["ask"] for a in js("list", "--all")["asks"]) == ["A1", "A2", "A2", "A3"]


def test_G7_2_P75_the_operator_typing_ok_on_a_doubled_id_is_told_not_dropped(home):
    first, later = doubled_log()
    t = home / "t.jsonl"
    t.write_text(json.dumps({"type": "custom-title", "customTitle": "API Server", "sessionId": SID}) + "\n")
    base = {"session_id": SID, "cwd": str(home), "transcript_path": str(t), "session_title": "API Server"}
    run("hook", "session-start", stdin=json.dumps(dict(base, hook_event_name="SessionStart", source="startup")))
    before = log_bytes()
    code, text = run("hook", "user-prompt-submit",
                     stdin=json.dumps(dict(base, hook_event_name="UserPromptSubmit", prompt="ok A2")))
    told = json.loads(text)["hookSpecificOutput"]["additionalContext"]
    assert code == 0 and log_bytes() == before
    assert "was not recorded" in told and first in told and later in told, told


# ---------------------------------------------------------------- other readers of line files

def test_G18_3_P75_uninstall_counts_an_ask_whose_title_holds_u2028(home):
    ok("add", "--title", "one MPLAIN", "--suggested", "y")
    with open(s.log_path(KEY), "ab") as f:
        f.write(old_line(ask="A2", title="two MLOST") + old_line(ask="A3", title="three\u0085MNEL"))
    assert leave.count_asks(s.home()) == (3, 3, 1)


def test_G3_2_P75_the_session_name_is_read_from_a_transcript_holding_raw_u2028(home):
    t = home / "t.jsonl"
    with open(t, "wb") as f:
        f.write(json.dumps({"type": "custom-title", "customTitle": "Old Name", "sessionId": SID}).encode() + b"\n")
        f.write(json.dumps({"type": "user", "text": "a b c\u0085d"}, ensure_ascii=False).encode() + b"\n")
        f.write(json.dumps({"type": "custom-title", "customTitle": "API Server", "sessionId": SID}).encode() + b"\n")
        f.write(json.dumps({"type": "user", "text": " " * 40}, ensure_ascii=False).encode() + b"\n")
    assert L.title_from_transcript(str(t)) == "API Server"


@pytest.mark.parametrize("edge", ("\u2028", "\u0085", "\u2029"), ids=["U+2028", "U+0085", "U+2029"])
def test_G1_1_P75_a_line_that_starts_or_ends_with_one_is_still_read(home, edge):
    """Hand-made: the character outside the JSON, at the very start and the very end of an event line."""
    s.ensure_home()
    a, b = old_line(ask="A1", title="one MSTART"), old_line(ask="A2", title="two MEND")
    with open(s.log_path(KEY), "ab") as f:
        f.write(edge.encode("utf-8") + a)
        f.write(b[:-1] + edge.encode("utf-8") + b"\n")
    events, bad = c.read_events(log_bytes())
    assert [e["ask"] for e in events] == ["A1", "A2"] and bad == 0
    assert "MSTART" in ok("board", "--plain") and "MEND" in ok("board", "--plain")
