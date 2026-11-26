"""P123 (#206, G11.2): a control character in an ask's text is shown as a visible mark by every view that writes the
text to a terminal, and by the reminder. The stored event is never changed, the exports are data and hold the text as
stored, and a tab and a line feed keep what each view does with them today.

Each test builds its own home. Every fault is collected and the list is the failure, so one run names every view and
field that still passes a character on."""
import csv
import io
import json
import re

import pytest

from pitboard import cli, flags

SID = "00000000-0000-4000-8000-000000000001"
MARK = "�"
CONTROL = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f]")           # every C0 but tab and line feed, DEL, every C1
OWN_COLOURS = sorted({v for v in flags.ANSI.values() if v} | {flags.RESET}, key=len, reverse=True)
ONE_OF_EACH = {"ESC": "\x1b", "C0, the first": "\x01", "C0, the bell": "\x07", "C0, backspace": "\x08",
               "C0, carriage return": "\r", "C0, the last": "\x1f", "DEL": "\x7f", "C1, the first": "\x80",
               "C1, next line": "\x85", "C1, the one-character CSI": "\x9b", "C1, the last": "\x9f"}
FIELDS = {"title": "ti", "suggested": "su", "why": "wh", "detail": "de", "hand": "ha", "step": "st", "lane": "la",
          "answer": "an", "note": "no", "reason": "re", "withdrawn": "wi", "deadline": "dl", "third": "th",
          "fourth": "fo", "changed": "ch", "json": "js", "none": "A9", "key": "ke"}


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("PITBOARD_HOME", str(tmp_path / "pb"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PITBOARD_TZ", "America/New_York")
    monkeypatch.setenv("PITBOARD_MACHINE", "studio-1")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(tmp_path / "env.sh"))
    monkeypatch.setenv("COLUMNS", "250")                        # wide: no text of the test is cut away
    for k in ("PITBOARD_LANE", "CLAUDE_CODE_SESSION_ID", "TMUX_PANE", "NO_COLOR", "PITBOARD_HUB_URL"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), stdout=out, stderr=err)
    return code, out.getvalue() + err.getvalue()


def hook(name, tmp, **more):
    obj = dict({"session_id": SID, "hook_event_name": name, "cwd": str(tmp), "transcript_path": str(tmp / "t.jsonl")},
               **more)
    out, real = io.StringIO(), cli.sys.stdin
    cli.sys.stdin = io.StringIO(json.dumps(obj))
    try:
        assert cli.main(["hook", name], stdout=out, stderr=io.StringIO()) == 0
    finally:
        cli.sys.stdin = real
    return out.getvalue()


def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)


def said(hook_output):
    """What a session reads of a hook's answer: every text in its JSON, decoded."""
    return "\n".join(strings(json.loads(hook_output))) if hook_output else ""


def text(field, c):
    """A text for `field` with the character inside it: two letters, the character, a tail that names the field."""
    return f"{FIELDS[field]}{c}zz-{field}"


def without_own_colours(s):
    for seq in OWN_COLOURS:
        s = s.replace(seq, "")
    return s


def world(tmp, monkeypatch, c):
    """One home with the character in every text field; every view's words, as (view, words, fields it must show)."""
    views = []

    def see(view, words, *must_show):
        views.append((view, words, must_show))

    def ok(result):
        code, out = result
        assert code == 0, out
        return out

    see("the reminder, nothing open", said(hook("session-start", tmp, source="startup", session_title=text("lane", c))),
        "lane")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SID)
    see("lane", ok(run("lane")), "lane")
    see("board, nothing open", ok(run("board")), "lane")
    see("add's own line", ok(run("add", "--title", text("title", c), "--suggested", text("suggested", c),
                                 "--why", text("why", c), "--detail", text("detail", c))), "title")
    see("add's own line, a hand ask", ok(run("add", "--kind", "hand", "--title", text("hand", c),
                                             "--step", text("step", c), "--step", "two")), "hand")
    see("add's own line, a third ask", ok(run("add", "--title", text("third", c), "--suggested", "s3")), "third")
    see("add's own line, a fourth ask", ok(run("add", "--title", text("fourth", c), "--suggested", "s4")), "fourth")
    see("board", ok(run("board")), "lane", "title", "suggested", "hand", "step")
    see("board --plain", ok(run("board", "--plain")), "lane", "title", "suggested", "hand", "step")
    see("list", ok(run("list")), "title", "hand")
    see("show A1", ok(run("show", "A1")), "lane", "title", "suggested", "why", "detail")
    see("show A2", ok(run("show", "A2")), "hand", "step")
    see("the reminder", said(hook("session-start", tmp, source="resume", session_title=text("lane", c))),
        "lane", "title", "suggested", "hand")
    see("the hint for a message that names an ask", said(hook("user-prompt-submit", tmp, prompt="what about A2 then")))
    see("the line that repeats a typed ok", said(hook("user-prompt-submit", tmp, prompt="ok A1")), "suggested")
    see("answer", ok(run("answer", "A2", "--answer", text("answer", c))))
    see("update", ok(run("update", "A3", "--title", text("changed", c))))
    see("withdraw", ok(run("withdraw", "A3", "--reason", text("reason", c))))
    see("done", ok(run("done", "A1", "--note", text("note", c))))
    see("board --all", ok(run("board", "--all")), "lane", "title", "suggested", "hand", "answer", "changed", "reason")
    see("list --all", ok(run("list", "--all")), "title", "hand", "answer", "changed", "reason")
    see("show A1, done", ok(run("show", "A1")), "title", "note")
    see("show A2, answered", ok(run("show", "A2")), "answer")
    see("show A3, withdrawn", ok(run("show", "A3")), "changed", "reason")
    code, out = run("add", "--title", "t", "--suggested", "s", "--deadline", text("deadline", c))
    assert code == 6, out
    see("a refusal that repeats the caller's words", out, "deadline")
    for command in (["show"], ["update", "--title", "x"], ["answer", "--answer", "x"], ["ok"], ["no"], ["done"],
                    ["withdraw", "--reason", "r"], ["reopen", "--reason", "r"]):
        code, out = run(command[0], "A9" + c + "zz-none", *command[1:])
        assert code != 0, out
        see(f"{command[0]}, refusing an ID that is none", out, "none")
    for command in (["list"], ["list", "--all"], ["board"], ["board", "--plain"], ["board", "--all"], ["lane"]):
        code, out = run(*command, "--lane", text("key", c))
        assert code == 3, out
        see(f"{' '.join(command)}, refusing a lane key that is none", out, "key")
        code, out = run(*command, "--json", "--lane", text("key", c))
        assert code == 3, out
        see(f"{' '.join(command)} --json, refusing a lane key that is none", json.loads(out)["message"], "key")
    as_json = json.loads(ok(run("add", "--title", text("json", c), "--suggested", "s", "--json")))
    see("add --json, its message", as_json["message"], "json")
    return views, as_json


def faults_in(views, c, name):
    faults = []
    escaped = json.dumps(c)[1:-1]                    # how `show` writes the character inside an event's JSON text
    for view, words, must_show in views:
        left = CONTROL.findall(without_own_colours(words))
        if left:
            faults.append(f"{name}: {view}: {len(left)} control character(s) written as they are")
        for field in must_show:
            if f"zz-{field}" not in words:
                faults.append(f"{name}: {view}: does not show the {field} text at all")
        for field, two in FIELDS.items():
            tail = f"zz-{field}"
            for m in re.finditer(re.escape(tail), words):
                before = words[: m.start()]
                if field == "lane" and before.endswith(two + "-"):
                    continue                         # the lane's key, made from its name: it never held the character
                if not (before.endswith(two + MARK) or (escaped != c and before.endswith(two + escaped))):
                    faults.append(f"{name}: {view}: the {field} text is not shown with the mark in the character's place")
                    break
    return faults


@pytest.mark.parametrize("name", list(ONE_OF_EACH))
def test_G11_2_P123_every_view_shows_a_control_character_as_a_visible_mark(home, monkeypatch, name):
    c = ONE_OF_EACH[name]
    views, _ = world(home, monkeypatch, c)
    faults = faults_in(views, c, name)
    assert not faults, f"{len(faults)} fault(s):\n" + "\n".join(faults)


def test_G11_2_P123_every_control_character_there_is_in_two_titles(home, monkeypatch):
    every = [chr(n) for n in list(range(9)) + list(range(11, 32)) + list(range(127, 160))]
    assert len(every) == 63 and all(CONTROL.fullmatch(ch) for ch in every)
    halves = (every[:32], every[32:])                           # a title holds 120 characters at most
    hook("session-start", home, source="startup", session_title="api")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SID)
    faults, added = [], []
    for half in halves:
        code, out = run("add", "--title", "a" + "b".join(half) + "z", "--suggested", "yes")
        assert code == 0, out
        added.append(out)
    for view, words in (("add's own lines", "".join(added)), ("board", run("board")[1]),
                        ("board --plain", run("board", "--plain")[1]), ("list", run("list")[1]),
                        ("board --all", run("board", "--all")[1]),
                        ("the reminder", said(hook("session-start", home, source="resume", session_title="api")))):
        left = CONTROL.findall(without_own_colours(words))
        if left:
            faults.append(f"{view}: {len(left)} of 63 control characters written as they are")
        for half in halves:
            if view == "add's own lines":
                continue                                        # that line is cut at 100 columns, as every line of add
            if "a" + "b".join(MARK for _ in half) + "z" not in words:
                faults.append(f"{view}: a title is not shown with one mark for each character and nothing else changed")
    assert not faults, f"{len(faults)} fault(s):\n" + "\n".join(faults)


def test_G11_2_P123_the_stored_event_and_the_exports_hold_the_text_as_it_was_given(home, monkeypatch):
    faults = []
    for name in ("ESC", "C0, the bell", "DEL", "C1, the one-character CSI"):
        c = ONE_OF_EACH[name]
        pb = home / ("pb-" + name.replace(" ", "-").replace(",", ""))
        monkeypatch.setenv("PITBOARD_HOME", str(pb))
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
        _, as_json = world(home, monkeypatch, c)
        logs = [p for p in (pb / "lanes").iterdir() if p.suffix == ".jsonl"]
        assert len(logs) == 1, logs
        events = [json.loads(ln) for ln in logs[0].read_text(encoding="utf-8").split("\n") if ln]
        stored = [s for e in events for s in strings(e.get("data"))]
        for field in ("title", "suggested", "why", "detail", "hand", "step", "answer", "reason", "note", "changed"):
            if text(field, c) not in stored:
                faults.append(f"{name}: the stored events do not hold the {field} text as it was given")
        if as_json["asks"][0]["title"] != text("json", c):
            faults.append(f"{name}: add --json: the ask in \"asks\" does not hold the title as it was given")
        code, out = run("export")
        exported = [s for ln in out.split("\n") if ln for s in strings(json.loads(ln))]
        if code != 0 or text("title", c) not in exported or text("step", c) not in exported:
            faults.append(f"{name}: export (JSONL) does not hold the text as stored")
        code, out = run("export", "--format", "csv")
        cells = [cell for row in csv.reader(io.StringIO(out, newline="")) for cell in row]
        if code != 0 or text("title", c) not in cells or text("suggested", c) not in cells:
            faults.append(f"{name}: export --format csv does not hold the text as stored")
    assert not faults, f"{len(faults)} fault(s):\n" + "\n".join(faults)


def test_G11_2_P123_a_tab_and_a_line_feed_are_shown_as_every_view_showed_them_before(home, monkeypatch):
    hook("session-start", home, source="startup", session_title="api")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SID)
    assert run("add", "--title", "one\ttwo", "--suggested", "four\nfive\tsix", "--why", "w1\nw2\tw3",
               "--detail", "d1\nd2\td3")[0] == 0
    assert run("add", "--kind", "hand", "--title", "pay", "--step", "s1\ns2\ts3")[0] == 0
    faults = []

    def holds(view, words, *parts):
        for part in parts:
            if part not in words:
                faults.append(f"{view}: no longer shows {part!r} as it did")
        if MARK in words:
            faults.append(f"{view}: a tab or a line feed is shown as the mark")

    holds("add's own line", run("add", "--title", "seven\teight", "--suggested", "s")[1], '"A3: seven\teight"')
    holds("board --plain", run("board", "--plain")[1], "  one\ttwo\n", "→ four\nfive\tsix\n", "1. s1\ns2\ts3\n")
    holds("show A1", run("show", "A1")[1], "title: one\ttwo\n", "suggested: four\nfive\tsix\n", "detail: d1\nd2\td3\n",
          "why: w1\nw2\tw3\n")
    holds("the reminder", said(hook("session-start", home, source="resume", session_title="api")),
          "] one\ttwo Suggested: four\nfive\tsix.\n")
    holds("the line that repeats a typed ok", said(hook("user-prompt-submit", home, prompt="ok A1")),
          'approved A1: "four\nfive\tsix".')
    assert run("answer", "A2", "--answer", "a1\na2\ta3")[0] == 0
    holds("board --all", run("board", "--all", "--plain")[1], "one\ttwo → four\nfive\tsix (ok)\n",
          "YOUR HAND: pay → a1\na2\ta3 (text)\n")
    assert not faults, f"{len(faults)} fault(s):\n" + "\n".join(faults)
