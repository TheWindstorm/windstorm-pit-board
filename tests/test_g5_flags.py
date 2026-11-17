"""G5: flags, colour and order. Test names carry the codon IDs (plan rule 2)."""
from datetime import datetime, timedelta, timezone

import pytest

from pitboard import contract as c
from pitboard import flags as f

NOW = datetime(2026, 11, 17, 19, 30, tzinfo=timezone.utc)


def ask(**kw):
    a = {"status": "open", "kind": "decision", "severity": "blocking", "deadline": None,
         "asked_at": c.ts_of(NOW - timedelta(hours=1)), "ask": "A1", "machine": "m", "lane_name": "L"}
    a.update(kw)
    return a


@pytest.mark.parametrize("kw,expect", [
    ({"status": "answered"}, f.CHEQUERED),
    ({"status": "done", "severity": "urgent"}, f.CHEQUERED),                 # row 1 before row 3
    ({"status": "withdrawn"}, f.GREY),
    ({"severity": "urgent"}, f.BLINK_RED),
    ({"severity": "can-wait", "deadline": c.ts_of(NOW + timedelta(hours=23))}, f.BLINK_RED),
    ({"severity": "can-wait", "deadline": c.ts_of(NOW - timedelta(hours=1))}, f.BLINK_RED),  # past
    ({"kind": "hand", "severity": "urgent"}, f.BLINK_RED),                   # row 3 before row 4
    ({"kind": "hand", "severity": "can-wait"}, f.BLUE),
    ({"kind": "hand", "deadline": c.ts_of(NOW + timedelta(hours=30))}, f.BLUE),
    ({"severity": "blocking"}, f.RED),
    ({"severity": "can-wait", "asked_at": c.ts_of(NOW - timedelta(hours=24))}, f.RED),
    ({"severity": "can-wait", "asked_at": c.ts_of(NOW - timedelta(hours=23))}, f.YELLOW),
])
def test_G5_1_flag_rows_in_order(kw, expect):
    assert f.flag(ask(**kw), NOW) == expect


def test_G5_1_config_hours():
    a = ask(severity="can-wait", asked_at=c.ts_of(NOW - timedelta(hours=5)))
    assert f.flag(a, NOW, escalate_after_hours=4) == f.RED
    b = ask(severity="can-wait", deadline=c.ts_of(NOW + timedelta(hours=30)))
    assert f.flag(b, NOW, urgent_deadline_hours=48) == f.BLINK_RED


def test_G5_1_ansi_codes():
    assert f.ANSI[f.BLINK_RED] == "\x1b[5;31m" and f.ANSI[f.RED] == "\x1b[31m"
    assert f.ANSI[f.BLUE] == "\x1b[34m" and f.ANSI[f.YELLOW] == "\x1b[33m" and f.ANSI[f.GREY] == "\x1b[90m"
    assert f.paint("x", f.RED) == "\x1b[31mx\x1b[0m"
    assert f.paint("x", f.CHEQUERED) == "x"


def test_G5_2_rank_and_worst():
    assert [k for k, _ in sorted(f.RANK.items(), key=lambda kv: kv[1])] == [
        f.BLINK_RED, f.RED, f.BLUE, f.YELLOW, f.CHEQUERED, f.GREY]
    asks = [ask(severity="can-wait"), ask(kind="hand"), ask(status="done", severity="urgent")]
    assert f.worst(asks, NOW) == f.BLUE
    assert f.worst([ask(status="done")], NOW) is None


def test_G5_3_plain_has_no_ansi():
    assert f.paint("x", f.BLINK_RED, plain=True) == "x"
    assert f.WORD[f.BLINK_RED] == "BLINK-RED" and f.WORD[f.CHEQUERED] == "DONE"
    assert "\x1b" not in f.label(f.RED)
    assert f.word(f.CHEQUERED, "answered") == "ANSWERED" and f.word(f.CHEQUERED, "done") == "DONE"
    assert f.label(f.CHEQUERED, "answered").endswith("ANSWERED")


def test_G5_4_sort_orders():
    t = lambda h: c.ts_of(NOW - timedelta(hours=h))  # noqa: E731
    a1 = ask(ask="A1", severity="can-wait", asked_at=t(1), lane_name="beta", machine="m2")
    a2 = ask(ask="A2", severity="blocking", asked_at=t(5), deadline=c.ts_of(NOW + timedelta(days=5)),
             lane_name="Alpha", machine="m1")
    a3 = ask(ask="A10", severity="blocking", asked_at=t(9), lane_name="alpha", machine="m1")
    a4 = ask(ask="A3", severity="urgent", asked_at=t(2), lane_name="beta", machine="m2")
    ids = lambda xs: [x["ask"] for x in xs]  # noqa: E731
    assert ids(f.sort_asks([a1, a2, a3, a4], "severity", NOW)) == ["A3", "A2", "A10", "A1"]
    assert ids(f.sort_asks([a1, a2, a3, a4], "deadline", NOW)) == ["A2", "A3", "A10", "A1"]
    assert ids(f.sort_asks([a1, a2, a3, a4], "age", NOW)) == ["A10", "A2", "A3", "A1"]
    assert ids(f.sort_asks([a1, a2, a3, a4], "lane", NOW)) == ["A2", "A10", "A1", "A3"]
    with pytest.raises(ValueError):
        f.sort_asks([a1], "random", NOW)
