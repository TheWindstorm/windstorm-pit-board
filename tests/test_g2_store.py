"""G2: store. Test names carry the codon IDs (plan rule 2). Every test uses a temporary PITBOARD_HOME."""
import json
import os
import stat
import subprocess
import sys
from datetime import timedelta

import pytest

from pitboard import contract as c
from pitboard import store as s

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PITBOARD_HOME", str(tmp_path / "pb"))
    for k in ("PITBOARD_MACHINE", "PITBOARD_TZ", "PITBOARD_HUB_URL", "PITBOARD_SELF_UPDATE"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path / "pb"


def asked_builder(title="Merge now?", severity="blocking", lane="api", lane_name="API"):
    def build(view):
        return c.make_event("asked", uid=c.new_id(), ask=view.next_ask_id(), lane=lane,
                            lane_name=lane_name, machine="studio-1", session_id="s1", by="agent",
                            data={"kind": "decision", "severity": severity, "title": title,
                                  "suggested": "yes", "source": "agent"})
    return build


def test_G2_1_home_from_env_mode_700(tmp_home):
    assert s.home() == str(tmp_home)
    s.ensure_home()
    assert stat.S_IMODE(os.stat(tmp_home).st_mode) == 0o700


def test_G2_1_default_home(monkeypatch):
    monkeypatch.delenv("PITBOARD_HOME")
    assert s.home() == os.path.join(os.path.expanduser("~"), ".pitboard")


def test_G2_2_file_names_use_the_key():
    assert s.log_path("api-server").endswith(os.path.join("lanes", "api-server.jsonl"))
    assert s.state_path("api-server").endswith(os.path.join("state", "api-server.json"))


def test_G2_3_lock_waits_then_lane_busy():
    s.ensure_home()
    with s.LaneLock("api", timeout=0.1):
        with pytest.raises(s.LaneBusy):
            with s.LaneLock("api", timeout=0.2):
                pass
    with s.LaneLock("api", timeout=0.1):  # released
        pass
    assert s.LOCK_WAIT_COMMAND == 3.0 and s.LOCK_WAIT_HOOK == 1.0


def test_G2_4_append_writes_lines_mode_600():
    written, _ = s.append("api", asked_builder())
    raw = open(s.log_path("api"), "rb").read()
    assert raw == c.serialize(written[0])
    assert stat.S_IMODE(os.stat(s.log_path("api")).st_mode) == 0o600


def test_G2_4_bad_event_writes_nothing():
    s.append("api", asked_builder())
    before = open(s.log_path("api"), "rb").read()
    with pytest.raises(c.ContractError):
        s.append("api", lambda v: [asked_builder()(v), asked_builder(title="")(v)])
    assert open(s.log_path("api"), "rb").read() == before


def test_INV1_appends_only():
    s.append("api", asked_builder())
    first = open(s.log_path("api"), "rb").read()
    s.append("api", asked_builder(title="Second?"))
    assert open(s.log_path("api"), "rb").read().startswith(first)


def test_G2_5_concurrent_writers_get_unique_ids(tmp_home):
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "from pitboard import contract as c, store as s\n"
        "def b(view):\n"
        "    return c.make_event('asked', uid=c.new_id(), ask=view.next_ask_id(), lane='api', lane_name='API',"
        " machine='m', session_id=None, by='agent', data={'kind':'decision','severity':'blocking',"
        "'title':'t','suggested':'y','source':'agent'})\n"
        "for _ in range(15): s.append('api', b, lock_timeout=10)\n" % ROOT)
    env = dict(os.environ, PITBOARD_HOME=str(tmp_home))
    procs = [subprocess.Popen([sys.executable, "-c", code], env=env) for _ in range(3)]
    assert all(p.wait(timeout=60) == 0 for p in procs)
    events, bad = s.read_log("api")
    ids = [e["ask"] for e in events]
    assert bad == 0 and len(ids) == 45 and len(set(ids)) == 45
    assert sorted(c.ask_number(i) for i in ids) == list(range(1, 46))


def test_G2_6_state_cache_shape_and_atomic_write():
    s.append("api", asked_builder())
    s.append("api", asked_builder(severity="urgent"))
    st = json.load(open(s.state_path("api")))
    for k in ("v", "lane", "lane_name", "machine", "built_at", "log_bytes", "open",
              "oldest_open_at", "worst_flag", "asks", "max_ask", "last_applied", "stats"):
        assert k in st
    assert st["open"] == 2 and st["worst_flag"] == "blinking-red" and st["lane_name"] == "API"
    assert st["log_bytes"] == s.log_size("api")
    assert not os.path.exists(s.state_path("api") + ".tmp")
    for k in ("uid", "ask", "status", "kind", "severity", "title", "suggested", "steps", "deadline",
              "asked_at", "answered_at", "answer", "done_at", "withdrawn_at", "updated_at", "source", "where",
              "session_id"):
        assert k in st["asks"][0]


def test_G2_7_stale_cache_is_rebuilt():
    s.append("api", asked_builder())
    # another writer appends without touching the cache
    ev = asked_builder(title="Out of band?")(s.View({}, 1))
    with open(s.log_path("api"), "ab") as f:
        f.write(c.serialize(c.prepare(ev)))
    st = s.read_state("api")
    assert st["open"] == 2 and st["log_bytes"] == s.log_size("api")


def test_G2_7_busy_lane_still_reads():
    s.append("api", asked_builder())
    os.remove(s.state_path("api"))
    with s.LaneLock("api", timeout=0.1):
        st = s.read_state("api", lock_timeout=0.05)
    assert st["open"] == 1


def test_G2_8_torn_last_line_is_ignored():
    s.append("api", asked_builder())
    with open(s.log_path("api"), "ab") as f:
        f.write(b'{"v":1,"event_id":"half')
    events, bad = s.read_log("api")
    assert len(events) == 1 and bad == 0


def test_G2_9_big_logs_are_reported(monkeypatch):
    s.append("api", asked_builder())
    monkeypatch.setattr(s, "BIG_LOG_BYTES", 10)
    assert s.big_logs() == ["api"]


def test_G2_10_config_defaults_file_and_env(tmp_home, monkeypatch):
    cfg = s.config()
    assert cfg["operator_name"] == "you" and cfg["escalate_after_hours"] == 24 and cfg["self_update"] is True
    assert c.MACHINE.match(cfg["machine"])
    s.ensure_home()
    with open(os.path.join(str(tmp_home), "config.json"), "w") as f:
        json.dump({"operator_name": "Grant", "display_tz": "America/New_York", "machine": "Studio One!",
                   "unknown_key": 1}, f)
    cfg = s.config()
    assert cfg["operator_name"] == "Grant" and cfg["machine"] == "studio-one" and "unknown_key" not in cfg
    monkeypatch.setenv("PITBOARD_MACHINE", "box-2")
    monkeypatch.setenv("PITBOARD_TZ", "America/Chicago")
    monkeypatch.setenv("PITBOARD_HUB_URL", "http://100.64.0.5:8765")
    monkeypatch.setenv("PITBOARD_SELF_UPDATE", "0")
    cfg = s.config()
    assert (cfg["machine"], cfg["display_tz"], cfg["hub_url"], cfg["self_update"]) == (
        "box-2", "America/Chicago", "http://100.64.0.5:8765", False)


def test_INV2_cache_can_be_deleted_without_loss():
    s.append("api", asked_builder())
    before = s.read_state("api")["asks"]
    os.remove(s.state_path("api"))
    assert s.read_state("api")["asks"] == before


# ---------------------------------------------------------------- plan 1.4: live-only cache, G2.11

def _close(view, ask_id, how="done"):
    a = view.find(ask_id)
    data = {"reason": "test"} if how in ("withdrawn", "reopened") else {}
    return c.make_event(how, uid=a["uid"], ask=a["ask"], lane="api", lane_name="API", machine="studio-1",
                        session_id="s1", by="operator", data=data)


def test_G2_6_cache_holds_live_asks_only_plus_max_ask():
    for _ in range(3):
        s.append("api", asked_builder())
    s.append("api", lambda v: _close(v, "A1"))
    st = s.read_state("api")
    assert sorted(a["ask"] for a in st["asks"]) == ["A2", "A3"]
    assert st["max_ask"] == 3 and st["last_applied"] and st["open"] == 2
    # the next ID still counts the closed ask
    ev, _ = s.append("api", asked_builder())
    assert ev[0]["ask"] == "A4"


def test_G2_11_incremental_cache_equals_full_fold():
    for i in range(6):
        s.append("api", asked_builder(title=f"Q{i}?"))
    s.append("api", lambda v: _close(v, "A2"))
    s.append("api", lambda v: _close(v, "A4", "withdrawn"))
    incremental = s.read_json(s.state_path("api"))
    os.remove(s.state_path("api"))
    rebuilt = s.read_state("api")
    for k in ("open", "max_ask", "last_applied", "worst_flag", "oldest_open_at", "log_bytes"):
        assert incremental[k] == rebuilt[k], k
    assert sorted(a["uid"] for a in incremental["asks"]) == sorted(a["uid"] for a in rebuilt["asks"])


def test_G2_11_event_for_a_closed_ask_refolds():
    s.append("api", asked_builder())
    s.append("api", lambda v: _close(v, "A1"))
    # reopen needs the closed ask: full=True gives build every ask
    _, st = s.append("api", lambda v: _close(v, "A1", "reopened"), full=True)
    assert [a["ask"] for a in st["asks"]] == ["A1"] and st["open"] == 1


def test_G2_11_catch_up_applies_only_new_lines():
    s.append("api", asked_builder())
    fold = s._Fold("api")
    first_end = fold.end
    s.append("api", asked_builder(title="Second?"))
    fold.catch_up()
    assert fold.end > first_end and len(fold.asks) == 2 and fold.stats["max_ask"] == 2


def test_G2_11_catch_up_refolds_when_a_line_sorts_earlier():
    s.append("api", asked_builder())
    s.append("api", asked_builder())
    fold = s._Fold("api")
    old = asked_builder(title="Old clock?")(s.View({}, 2))
    old["ts"] = "2000-01-01T00:00:00.000Z"
    with open(s.log_path("api"), "ab") as f:
        f.write(c.serialize(c.prepare(old)))
    fold.catch_up()
    assert len(fold.asks) == 3 and fold.stats["max_ask"] == 3
    events, _ = s.read_log("api")
    assert fold.asks.keys() == c.fold(events)[0].keys()


def test_G2_11_view_full_has_every_ask_and_event():
    s.append("api", asked_builder())
    s.append("api", lambda v: _close(v, "A1"))
    seen = {}

    def build(view):
        seen["full"], seen["asks"], seen["events"] = view.full, len(view.asks), len(view.events)
        return []
    s.append("api", build, full=True)
    assert seen == {"full": True, "asks": 1, "events": 2}


def test_G2_11_append_on_a_20MB_log_under_200ms():
    """Plan 1.4 G2.11: with a fresh cache an append never reads the whole log."""
    import time
    s.ensure_home()
    # one asked and one done line, checked once, then copied with new ids (masking 45k lines is slow)
    a = c.prepare(c.make_event("asked", uid="f" * 32, ask="A1", lane="api", lane_name="API", machine="studio-1",
                               session_id="s1", by="agent",
                               data={"kind": "decision", "severity": "can-wait", "title": "Q?",
                                     "detail": "x" * 300, "suggested": "yes", "source": "agent"}))
    d = c.prepare(c.make_event("done", uid="f" * 32, ask="A1", lane="api", lane_name="API", machine="studio-1",
                               session_id="s1", by="operator", data={}))
    a["ts"], d["ts"] = "2026-01-01T00:00:00.000Z", "2026-01-01T00:00:01.000Z"
    ta, td = c.serialize(a).decode(), c.serialize(d).decode()
    chunks, size, n = [], 0, 0
    while size < 20 * 1024 * 1024:
        n += 1
        uid = c.new_id()
        for tpl in (ta, td):
            raw = (tpl.replace("f" * 32, uid).replace(a["event_id"], c.new_id())
                   .replace(d["event_id"], c.new_id()).replace('"ask":"A1"', f'"ask":"A{n}"'))
            chunks.append(raw)
            size += len(raw)
    with open(s.log_path("api"), "w", encoding="utf-8") as f:
        f.write("".join(chunks))
    st = s.read_state("api")  # one full build
    assert st["max_ask"] == n and st["open"] == 0 and st["stats"]["invalid"] == 0
    times = []
    for _ in range(3):
        t0 = time.perf_counter()
        s.append("api", asked_builder())
        times.append(time.perf_counter() - t0)
    st = s.read_json(s.state_path("api"))
    assert st["max_ask"] == n + 3 and st["open"] == 3
    print(f"G2.11 append ms: {[round(x * 1000) for x in times]}")
    assert min(times) < 0.2, f"append took {min(times) * 1000:.0f} ms on a {size // 1048576} MB log"


# ---------------------------------------------------------------- G2.12

@pytest.fixture
def frozen_clock(monkeypatch):
    """Every event in the same millisecond, with event IDs that sort newest first:
    the worst case for G1.11's (ts, event_id) order."""
    ids = iter(f"{n:032x}" for n in range(10 ** 6, 0, -1))
    monkeypatch.setattr(c, "now_ts", lambda: "2026-11-17T21:00:00.000Z")
    monkeypatch.setattr(c, "new_id", lambda: next(ids))


def test_G2_12_done_then_reopen_in_one_millisecond_keep_their_order(frozen_clock):
    s.append("api", asked_builder())
    s.append("api", lambda v: _close(v, "A1"))
    _, st = s.append("api", lambda v: _close(v, "A1", "reopened"), full=True)
    assert [a["ask"] for a in st["asks"]] == ["A1"] and st["open"] == 1
    events, _ = s.read_log("api")
    stamps = [e["ts"] for e in events]
    assert stamps == ["2026-11-17T21:00:00.000Z", "2026-11-17T21:00:00.001Z", "2026-11-17T21:00:00.002Z"]
    assert c.fold(events)[0][events[0]["uid"]]["status"] == "open"           # a reader's full fold agrees


def test_G2_12_events_of_one_append_are_spaced(frozen_clock):
    def two(v):
        first = asked_builder()(v)
        second = c.make_event("done", uid=first["uid"], ask=first["ask"], lane="api", lane_name="API",
                              machine="studio-1", session_id="s1", by="agent", data={})
        return [first, second]
    s.append("api", asked_builder(title="Before?"))
    written, _ = s.append("api", two)
    assert [e["ts"] for e in written] == ["2026-11-17T21:00:00.001Z", "2026-11-17T21:00:00.002Z"]


def test_G2_12_other_clocks_and_hub_events_keep_their_ts(monkeypatch):
    s.append("api", asked_builder())
    newest = s.read_state("api")["last_applied"][0]
    late = c.ts_of(c.parse_ts(newest) - timedelta(seconds=5))          # another machine, 5 s behind
    monkeypatch.setattr(c, "now_ts", lambda: late)
    written, _ = s.append("api", asked_builder(title="Slow clock?"))
    assert written[0]["ts"] == late
    hub = asked_builder(title="From the page?")
    def from_hub(v):
        ev = hub(v)
        ev["origin"], ev["ts"] = "hub", newest
        return ev
    written, _ = s.append("api", from_hub)
    assert written[0]["ts"] == newest
