"""G11: the board view (and pitboard list). Fixed clock, New York display zone."""
import io
import re
from datetime import datetime, timedelta, timezone

import pytest

from pitboard import cli, contract as c, flags, render as R, timefmt

NY = timefmt.zone("America/New_York")
NOW = datetime(2026, 11, 17, 19, 4, tzinfo=timezone.utc)          # 2:04 PM ET
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def ask(n, title, hours_ago=1.0, status="open", **kw):
    a = {"uid": f"{n:032x}", "ask": f"A{n}", "status": status, "kind": "question", "severity": "blocking",
         "title": title, "suggested": "", "steps": [], "deadline": None,
         "asked_at": c.ts_of(NOW - timedelta(hours=hours_ago)), "answer": None, "answered_via": None,
         "answered_at": None, "done_at": None, "withdrawn_at": None, "withdrawn_reason": None,
         "machine": "m", "lane_name": "API Server"}
    a.update(kw)
    return a


def plan_example():
    return [
        ask(12, "Merge #651 now or wait for review?", 49, suggested="merge now (CI green, no shared files)"),
        ask(14, "create a Stripe account", 5, kind="hand", deadline="2026-11-19T22:00:00.000Z",
            steps=["Go to stripe.com/register", "Use the company email", "Paste the key name here"],
            severity="can-wait"),
        ask(15, "Keep the old pricing page?", 3, severity="can-wait", suggested="no, redirect it to /pricing"),
    ]


def test_G11_1_open_view_matches_the_plan_example():
    # the plan's step line is 101 columns, so this check runs at 110 (G11.4 cutting is tested below)
    text = R.board_open(plan_example(), "API Server", NY, NOW, width=110, plain=True)
    assert text.splitlines() == [
        "PIT BOARD · API Server · 3 open · 2:04 PM ET",
        "A12 🔴 RED     2d  Merge #651 now or wait for review?",
        "                   → merge now (CI green, no shared files)",
        "A14 🔵 BLUE    5h  YOUR HAND: create a Stripe account · due Thu 5:00 PM ET",
        "                   1. Go to stripe.com/register  2. Use the company email  3. Paste the key name here",
        "A15 🟡 YELLOW  3h  Keep the old pricing page?",
        "                   → no, redirect it to /pricing",
        "Answer: ok A12 A15 · no A15 · or just reply · pb all = history",
    ]


def test_G11_2_nothing_waits():
    assert R.board_open([ask(1, "x", status="done")], "API Server", NY, NOW) == \
        "PIT BOARD · API Server · nothing waits on you · 2:04 PM ET"


def test_G11_2_hint_without_suggested_answers():
    text = R.board_open([ask(1, "Plug in", kind="hand", steps=["Plug it in"])], "L", NY, NOW, plain=True)
    assert text.splitlines()[-1] == "Answer: just reply · pb all = history"


def test_G11_3_history_oldest_first_closed_rows():
    asks = [
        ask(9, "Use staging first?", 120, status="done", answer="yes", answered_via="ok",
            answered_at="2026-11-12T15:00:00.000Z", done_at="2026-11-12T16:00:00.000Z"),
        ask(10, "Old idea?", 100, status="withdrawn", withdrawn_at="2026-11-13T15:00:00.000Z",
            withdrawn_reason="moot"),
        ask(11, "Ship it?", 2, status="answered", answer="Yes", answered_via="text",
            answered_at="2026-11-17T18:00:00.000Z"),
        ask(12, "Still open?", 1),
    ]
    lines = R.board_history(list(reversed(asks)), "API Server", NY, NOW, plain=True).splitlines()
    assert lines[0].startswith("PIT BOARD · API Server · history · 4 asks")
    assert lines[1] == "A9  🏁 DONE      Nov 12  Use staging first? → yes (ok)"
    assert lines[2] == "A10 ⚪ GREY      Nov 13  Old idea? → withdrawn: moot"
    assert lines[3] == "A11 🏁 ANSWERED  Nov 17  Ship it? → Yes (text)"
    assert lines[4].startswith("A12 🔴 RED")                      # newest at the bottom
    assert len(lines) == 6


def test_G11_3_limit_keeps_the_newest_and_0_shows_all():
    asks = [ask(n, f"Q{n}?", 200 - n, status="done") for n in range(1, 61)]
    lines = R.board_history(asks, "L", NY, NOW, plain=True).splitlines()
    assert len(lines) == 50 + 2 and lines[1].startswith("A11 ") and lines[-2].startswith("A60 ")
    assert "(newest 50)" in lines[0]
    assert len(R.board_history(asks, "L", NY, NOW, limit=0).splitlines()) == 62
    assert len(R.board_history(asks, "L", NY, NOW, limit=5).splitlines()) == 7


def test_G11_4_width_flag_then_COLUMNS_then_100():
    assert R.width_of(None, {}) == 100
    assert R.width_of(None, {"COLUMNS": "80"}) == 80
    assert R.width_of(60, {"COLUMNS": "80"}) == 60
    assert R.width_of(None, {"COLUMNS": "junk"}) == 100


def test_G11_4_every_line_fits_counting_emoji_as_two():
    asks = plan_example() + [ask(16, "word " * 60, 1, suggested="s " * 80)]
    for width in (40, 72, 100):
        for text in (R.board_open(asks, "API Server", NY, NOW, width=width),
                     R.board_history(asks, "API Server", NY, NOW, width=width)):
            for ln in text.splitlines():
                assert R.cols(ANSI.sub("", ln)) <= width, (width, ln)
    assert R.cols("🔴 RED") == 6 and R.cut("🔴🔴🔴", 5) == "🔴🔴…"


def test_G11_4_open_view_at_most_30_asks_then_more_line():
    asks = [ask(n, f"Q{n}?", 1, suggested="yes") for n in range(1, 41)]
    lines = R.board_open(asks, "L", NY, NOW, plain=True).splitlines()
    assert len(lines) == 2 * 30 + 3 and lines[-2] == "(+10 more: pitboard list)"


def test_G11_colour_only_on_the_flag_and_none_when_plain():
    text = R.board_open(plan_example(), "API Server", NY, NOW)
    assert flags.ANSI[flags.RED] + "🔴 RED" + flags.RESET in text
    assert ANSI.sub("", text) == R.board_open(plan_example(), "API Server", NY, NOW, plain=True)
    assert R.plain_wanted(False, {"NO_COLOR": ""}) and not R.plain_wanted(False, {})
    narrow = R.board_open(plan_example(), "API Server", NY, NOW, width=8)  # flag cut away: no stray codes
    assert not re.search(r"\x1b\[[0-9;]*m(?!.*\x1b\[0m)", narrow)


# ---------------------------------------------------------------- the commands

@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("PITBOARD_HOME", str(tmp_path / "pb"))
    monkeypatch.setenv("PITBOARD_TZ", "America/New_York")
    monkeypatch.setenv("PITBOARD_MACHINE", "studio-1")
    for k in ("PITBOARD_LANE", "CLAUDE_CODE_SESSION_ID", "TMUX_PANE", "COLUMNS", "NO_COLOR"):
        monkeypatch.delenv(k, raising=False)


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    return cli.main(list(argv), stdout=out, stderr=err), out.getvalue(), err.getvalue()


def test_G11_board_and_list_commands(home, monkeypatch):
    for t in ("First?", "Second?", "Third?"):
        run("add", "--lane", "api", "--title", t, "--suggested", "yes", "--severity", "can-wait")
    run("done", "A2", "--lane", "api")
    code, out, _ = run("board", "--lane", "api", "--plain")
    assert code == 0 and out.splitlines()[0].startswith("PIT BOARD · api · 2 open")
    assert "Answer: ok A1 A3 · no A3" in out and "Second?" not in out
    code, out, _ = run("board", "--lane", "api", "--all", "--plain", "--limit", "0")
    assert [ln.split()[0] for ln in out.splitlines()[1:-1]] == ["A1", "A2", "A3"]
    code, out, _ = run("list", "--lane", "api")
    assert code == 0 and len(out.splitlines()) == 2 and "\x1b[" in out
    monkeypatch.setenv("NO_COLOR", "1")
    code, out, _ = run("list", "--lane", "api", "--all", "--sort", "age")
    assert [ln.split()[0] for ln in out.splitlines()] == ["A1", "A2", "A3"] and "\x1b[" not in out
    monkeypatch.setenv("COLUMNS", "30")
    _, out, _ = run("board", "--lane", "api")
    assert max(R.cols(ln) for ln in out.splitlines()) <= 30
    assert run("board", "--lane", "api", "--limit", "-1")[0] == 2
