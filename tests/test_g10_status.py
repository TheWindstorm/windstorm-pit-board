"""G10: the status line segment."""
import io
import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from pitboard import cli, contract as c, flags, lane as L, render as R, store as s

SID = "0f3a9c2e-1b2c-4d5e-8f90-123456789abc"
NOW = datetime(2026, 11, 17, 19, 4, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("PITBOARD_HOME", str(tmp_path / "pb"))
    monkeypatch.setenv("PITBOARD_MACHINE", "studio-1")
    for k in ("PITBOARD_LANE", "CLAUDE_CODE_SESSION_ID", "TMUX_PANE", "NO_COLOR"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path / "pb"


def ask(n, hours_ago, status="open", **kw):
    a = {"uid": f"{n:032x}", "ask": f"A{n}", "status": status, "kind": "question", "severity": "can-wait",
         "deadline": None, "asked_at": c.ts_of(NOW - timedelta(hours=hours_ago))}
    a.update(kw)
    return a


def status(stdin_obj=None, *argv):
    out, err = io.StringIO(), io.StringIO()
    stdin = io.StringIO(json.dumps(stdin_obj) if stdin_obj is not None else "")
    real = cli.sys.stdin
    cli.sys.stdin = stdin
    try:
        code = cli.main(["status", *argv], stdout=out, stderr=err)
    finally:
        cli.sys.stdin = real
    return code, out.getvalue(), err.getvalue()


def add(title="Go?", lane_key="api-server", **kw):
    args = ["add", "--lane", lane_key, "--title", title, "--suggested", "yes"]
    for k, v in kw.items():
        args += [f"--{k}", v]
    assert cli.main(args, stdout=io.StringIO(), stderr=io.StringIO()) == 0


# ---------------------------------------------------------------- G10.2 segment

def test_G10_2_nothing_open_prints_nothing():
    assert R.status_segment({"asks": []}, NOW) == ""
    assert R.status_segment({"asks": [ask(1, 5, status="done")]}, NOW) == ""
    assert R.status_segment(None, NOW) == ""


def test_G10_2_count_oldest_and_worst_colour():
    st = {"asks": [ask(1, 49, severity="blocking"), ask(2, 3), ask(3, 1)]}
    seg = R.status_segment(st, NOW)
    assert seg == flags.ANSI[flags.RED] + "🔴 3 asks · oldest 2d" + flags.RESET
    assert R.status_segment({"asks": [ask(1, 3)]}, NOW, plain=True) == "🟡 YELLOW 1 ask · oldest 3h"


def test_G10_2_blinking_red_makes_the_whole_segment_blink():
    st = {"asks": [ask(1, 2), ask(2, 1, severity="urgent")]}
    seg = R.status_segment(st, NOW)
    assert seg.startswith("\x1b[5;31m") and seg.endswith(flags.RESET) and "2 asks" in seg


# ---------------------------------------------------------------- G10.1, G10.4, G10.6 command

def test_G10_1_finds_the_lane_from_session_id_no_newline():
    L.resolve(SID, "API Server")
    add()
    code, out, err = status({"session_id": SID})
    assert code == 0 and err == "" and out.endswith("ask · oldest 0m" + flags.RESET) and not out.endswith("\n")


def test_G10_1_flag_or_env_without_stdin(monkeypatch):
    add()
    assert "1 ask" in status(None, "--lane", "api-server")[1]
    monkeypatch.setenv("PITBOARD_LANE", "api-server")
    assert "1 ask" in status(None)[1]


def test_G10_2_lane_with_nothing_open_prints_nothing():
    L.resolve(SID, "API Server")
    add()
    cli.main(["done", "A1", "--lane", "api-server"], stdout=io.StringIO(), stderr=io.StringIO())
    assert status({"session_id": SID}) == (0, "", "")


@pytest.mark.parametrize("stdin", [{"session_id": "unknown"}, {"session_id": 7}, [1, 2], None])
def test_G10_4_unknown_or_bad_input_prints_nothing(stdin):
    assert status(stdin) == (0, "", "")


def test_G10_4_errors_print_nothing(monkeypatch):
    L.resolve(SID, "API Server")
    add()

    def boom(*a, **k):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(s, "read_state", boom)
    assert status({"session_id": SID}) == (0, "", "")


def test_G10_6_session_name_sets_lane_name_once_a_minute(home, monkeypatch):
    L.resolve(SID, "API Server")
    add()
    status({"session_id": SID, "session_name": "Renamed Lane"})
    row = L.read_map()[SID]
    assert row["lane"] == "api-server" and row["lane_name"] == "Renamed Lane"
    seen = json.loads((home / "state" / "statusline-seen.json").read_text())
    assert c.TS.match(seen[SID])
    status({"session_id": SID, "session_name": "Too Soon"})
    assert L.read_map()[SID]["lane_name"] == "Renamed Lane"
    monkeypatch.setattr(cli, "STATUSLINE_SEEN_SECONDS", 0)
    status({"session_id": SID, "session_name": "Later"})
    assert L.read_map()[SID]["lane_name"] == "Later" and L.read_map()[SID]["lane"] == "api-server"


def test_G10_3_fast_on_a_warm_cache():
    L.resolve(SID, "API Server")
    for i in range(30):
        add(title=f"Q{i}?")
    status({"session_id": SID})
    best = 1e9
    for _ in range(5):
        t = time.perf_counter()
        status({"session_id": SID})
        best = min(best, time.perf_counter() - t)
    assert best < 0.05, f"{best * 1000:.0f} ms"


def test_G10_3_status_reads_no_log_when_the_cache_is_fresh(monkeypatch):
    L.resolve(SID, "API Server")
    add()
    status({"session_id": SID})

    def no_log(*a, **k):
        raise AssertionError("the log was read")
    monkeypatch.setattr(s, "read_from", no_log)
    assert "1 ask" in status({"session_id": SID})[1]
