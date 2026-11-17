"""G3: lane identity. Every test uses a temporary PITBOARD_HOME."""
import json
import os
import subprocess
import sys

import pytest

from pitboard import contract as c
from pitboard import lane as L
from pitboard import store as s

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SID = "0f3a9c2e-1b2c-4d5e-8f90-123456789abc"


@pytest.fixture(autouse=True)
def tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PITBOARD_HOME", str(tmp_path / "pb"))
    for k in ("PITBOARD_LANE", "CLAUDE_CODE_SESSION_ID"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path / "pb"


@pytest.mark.parametrize("name,key", [
    ("Windstorm Pitboard", "windstorm-pitboard"),
    ("  API -- server!! ", "api-server"),
    ("Ünïcode Lane 2", "n-code-lane-2"),
    ("a" * 70, "a" * 64),
    ("x" * 63 + " y", "x" * 63),         # cut leaves no trailing '-'
])
def test_G3_1_key_form(name, key):
    k = L.key_of(name, SID)
    assert k == key and c.LANE_KEY.match(k)


@pytest.mark.parametrize("name", [None, "", "!!!", "  "])
def test_G3_1_empty_name_uses_session_prefix(name):
    assert L.key_of(name, SID) == "session-0f3a9c2e"


def _transcript(tmp_path, records, pad_lines=0):
    p = tmp_path / "t.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
            for _ in range(pad_lines):
                f.write(json.dumps({"type": "user", "message": "x" * 500}) + "\n")
    return str(p)


def test_G3_2_newest_custom_title_wins(tmp_path):
    p = _transcript(tmp_path, [
        {"type": "custom-title", "customTitle": "Windstorm Scribe", "sessionId": SID},
        {"type": "user", "message": "mentions \"custom-title\" in text"},
        {"type": "custom-title", "customTitle": "Windstorm Pitboard", "sessionId": SID},
    ], pad_lines=3000)  # ~1.5 MB per gap: crosses the 1 MB read chunks
    assert L.title_from_transcript(p) == "Windstorm Pitboard"
    assert L.lane_name(None, p) == "Windstorm Pitboard"


def test_G3_2_record_cut_by_chunk_edge_is_still_found(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "CHUNK", 7)
    p = _transcript(tmp_path, [{"type": "custom-title", "customTitle": "Edge Case"}, {"type": "user"}])
    assert L.title_from_transcript(p) == "Edge Case"


def test_G3_2_no_rename_no_file_bad_lines(tmp_path):
    p = _transcript(tmp_path, [{"type": "user"}])
    assert L.lane_name(None, p) is None
    assert L.lane_name(None, str(tmp_path / "missing.jsonl")) is None
    assert L.lane_name(None, None) is None
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"type": "custom-title", broken\n{"type":"custom-title","customTitle":"  "}\n')
    assert L.title_from_transcript(str(bad)) is None


def test_G3_2_session_title_first_C3_confirmed(tmp_path, monkeypatch):
    p = _transcript(tmp_path, [{"type": "custom-title", "customTitle": "From Rename"}])
    assert L.SESSION_TITLE_IS_RENAME is True                   # C3: session_title is the rename name
    assert L.lane_name("Confirmed title", p) == "Confirmed title"
    # a --name session at its first SessionStart: no custom-title record in the transcript yet
    (tmp_path / "named").mkdir()
    empty = _transcript(tmp_path / "named", [{"type": "user"}])
    assert L.lane_name("Windstorm Pitboard", empty) == "Windstorm Pitboard"
    assert L.key_of(L.lane_name("Windstorm Pitboard", empty), SID) == "windstorm-pitboard"
    # never named: no session_title (C3), so the transcript step, then the session- key
    assert L.lane_name(None, p) == "From Rename" and L.lane_name("  ", p) == "From Rename"
    monkeypatch.setattr(L, "SESSION_TITLE_IS_RENAME", False)
    assert L.lane_name("Confirmed title", p) == "From Rename"


def test_G3_3_map_shape_and_atomic_lock(tmp_home):
    row = L.resolve(SID, "Windstorm Pitboard")
    assert set(row) == {"lane", "lane_name", "first_seen", "last_seen"}
    assert c.TS.match(row["first_seen"]) and row["first_seen"] == row["last_seen"]
    m = json.loads((tmp_home / "lanes.json").read_text())
    assert m[SID]["lane"] == "windstorm-pitboard"
    assert (tmp_home / "lanes.json.lock").exists() and not (tmp_home / "lanes.json.tmp").exists()
    with s.LaneLock(None, timeout=0.1, path=L.map_lock_path()):
        with pytest.raises(s.LaneBusy):
            L.resolve(SID, "x", lock_timeout=0.1)


def test_G3_4_first_sight_wins_rename_changes_name_only():
    first = L.resolve(SID, None)
    assert first["lane"] == "session-0f3a9c2e"
    again = L.resolve(SID, "Windstorm Pitboard")
    assert again["lane"] == "session-0f3a9c2e" and again["lane_name"] == "Windstorm Pitboard"
    later = L.resolve(SID, None)  # no name given: the stored name stays
    assert later["lane_name"] == "Windstorm Pitboard" and later["first_seen"] == first["first_seen"]


def test_G3_5_same_name_new_session_joins_the_lane():
    a = L.resolve(SID, "API Server")
    b = L.resolve("11111111-2222-3333-4444-555555555555", "api server")
    assert a["lane"] == b["lane"] == "api-server"


def test_G3_5_two_live_sessions_one_lane_unique_ids():
    """Two sessions under one name append to one log; the lane lock keeps short IDs unique."""
    for sid in (SID, "22222222-0000-0000-0000-000000000000"):
        key = L.resolve(sid, "Shared")["lane"]
        code = (
            "from pitboard import contract as c, store as s\n"
            "for _ in range(15):\n"
            "    s.append(%r, lambda v: c.make_event('asked', uid=c.new_id(), ask=v.next_ask_id(), lane=%r,"
            " lane_name='Shared', machine='m', session_id=%r, by='agent', data={'kind': 'decision',"
            " 'severity': 'can-wait', 'title': 'Q?', 'suggested': 'yes', 'source': 'agent'}))\n"
        ) % (key, key, sid)
        procs = [subprocess.Popen([sys.executable, "-c", code], cwd=ROOT) for _ in range(2)]
        assert all(p.wait(timeout=60) == 0 for p in procs)
    events, bad = s.read_log("shared")
    asks = [e["ask"] for e in events]
    assert bad == 0 and len(asks) == 60 and len(set(asks)) == 60


def test_G3_6_lane_adopt_is_removed():
    assert not hasattr(L, "adopt")


def test_G3_7_order_flag_env_session_then_error(monkeypatch):
    L.resolve(SID, "From Session")
    env = {"PITBOARD_LANE": "from-env", "CLAUDE_CODE_SESSION_ID": SID}
    assert L.find("from-flag", env) == "from-flag"
    assert L.find(None, env) == "from-env"
    assert L.find(None, {"CLAUDE_CODE_SESSION_ID": SID}) == "from-session"
    with pytest.raises(L.NoLane) as e:
        L.find(None, {"CLAUDE_CODE_SESSION_ID": "unknown"})
    assert e.value.exit_code == 3
    assert str(e.value) == "pitboard: which lane? Pass --lane KEY. Lanes on this machine: none yet"


def test_G3_7_error_lists_the_lanes_and_reads_os_environ(monkeypatch):
    for k in ("b-lane", "a-lane"):
        s.append(k, lambda v, k=k: c.make_event(
            "asked", uid=c.new_id(), ask=v.next_ask_id(), lane=k, lane_name=k, machine="m", session_id=None,
            by="agent", data={"kind": "decision", "severity": "can-wait", "title": "Q?", "suggested": "yes",
                              "source": "agent"}))
    with pytest.raises(L.NoLane) as e:
        L.find()
    assert str(e.value).endswith("Lanes on this machine: a-lane, b-lane")
    monkeypatch.setenv("PITBOARD_LANE", "a-lane")
    assert L.find() == "a-lane"
    with pytest.raises(L.NoLane):
        L.find("Not A Key")
