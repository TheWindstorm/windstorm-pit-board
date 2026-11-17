"""G6: the pitboard command. Every test uses a temporary PITBOARD_HOME."""
import csv
import io
import json
import os
import subprocess
import sys

import pytest

from pitboard import cli, contract as c, lane as L, store as s

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SID = "0f3a9c2e-1b2c-4d5e-8f90-123456789abc"


@pytest.fixture(autouse=True)
def tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PITBOARD_HOME", str(tmp_path / "pb"))
    monkeypatch.setenv("PITBOARD_MACHINE", "studio-1")
    monkeypatch.setenv("PITBOARD_TZ", "America/New_York")
    for k in ("PITBOARD_LANE", "CLAUDE_CODE_SESSION_ID", "TMUX_PANE", "PITBOARD_HUB_URL"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path / "pb"


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def js(*argv):
    code, out, err = run(*argv, "--json")
    assert err == ""
    obj = json.loads(out)
    assert set(obj) == {"ok", "exit", "message", "ids", "asks", "data"} and obj["exit"] == code
    return obj


def add(*extra, title="Merge #651 now?", lane="api"):
    return run("add", "--lane", lane, "--title", title, "--suggested", "Yes", *extra)


# ---------------------------------------------------------------- G6.1

def test_G6_1_bin_pitboard_runs_the_launcher(tmp_home):
    env = dict(os.environ, PITBOARD_HOME=str(tmp_home), HOME=str(tmp_home.parent / "home"))
    r = subprocess.run([os.path.join(ROOT, "bin", "pitboard"), "add", "--lane", "api", "--title", "Go?",
                        "--suggested", "yes"], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0 and r.stdout.startswith("A1 recorded"), r.stderr
    with open(os.path.join(ROOT, "bin", "pitboard"), encoding="utf-8") as f:
        src = f.read()
    assert src.startswith("#!/bin/sh") and '"$(dirname "$0")/../pitboard/launch.py"' in src
    assert os.access(os.path.join(ROOT, "bin", "pitboard"), os.X_OK)


# ---------------------------------------------------------------- G6.2

def test_G6_2_add_text_and_defaults():
    code, out, _ = add()
    assert code == 0 and out == 'A1 recorded (RED). Ask it in chat as: "A1: Merge #651 now?"\n'
    a = s.read_state("api")["asks"][0]
    assert (a["kind"], a["severity"], a["source"]) == ("question", "blocking", "agent")
    ev = s.read_log("api")[0][0]
    assert ev["by"] == "agent" and ev["type"] == "asked"


def test_G6_2_json_shape_for_every_command():
    add()
    for argv in (("update", "A1", "--why", "deploy"), ("answer", "A1", "--answer", "yes"), ("done", "A1"),
                 ("reopen", "A1", "--reason", "again"), ("ok", "A1"), ("withdraw", "A1", "--reason", "moot"),
                 ("show", "A1"), ("lane",), ("version",), ("export",)):
        obj = js(*argv, "--lane", "api")
        assert obj["ok"] is True, (argv, obj)
    assert js("lane", "--lane", "api")["data"] == {"lane": "api", "lane_name": "api"}
    assert set(js("version")["data"]) == {"running", "installed", "pinned", "generation"}
    bad = js("done", "A9", "--lane", "api")
    assert bad["ok"] is False and bad["exit"] == 4


def test_G6_2_update_answer_no_done_withdraw_reopen_texts():
    add()
    add(title="Second?")
    assert run("update", "A1", "--lane", "api", "--severity", "can-wait")[1] == "A1 updated.\n"
    assert run("answer", "A1", "--lane", "api", "--answer", "Yes, merge it")[1] == "A1 answered.\n"
    assert run("no", "A2", "--lane", "api")[1] == "Declined: A2.\n"
    assert run("done", "A1", "--lane", "api", "--note", "merged")[1] == "A1 done.\n"
    assert run("reopen", "A1", "--lane", "api", "--reason", "reverted")[1] == "A1 reopened.\n"
    assert run("withdraw", "A1", "--lane", "api", "--reason", "moot")[1] == "A1 withdrawn.\n"
    asks = s.all_asks("api")
    by = {a["ask"]: a for a in asks.values()}
    assert by["A1"]["status"] == "withdrawn" and by["A1"]["severity"] == "can-wait"
    assert by["A2"]["answer"] == "No." and by["A2"]["answered_via"] == "no" and by["A2"]["answered_by"] == "operator"


def test_G6_2_answer_default_by_agent_and_via_text():
    add()
    run("answer", "A1", "--lane", "api", "--answer", "Operator said yes")
    a = s.read_state("api")["asks"][0]
    assert (a["answered_by"], a["answered_via"], a["answer"]) == ("agent", "text", "Operator said yes")


def test_G6_2_ok_list_and_all_with_skips():
    add()
    run("add", "--lane", "api", "--kind", "hand", "--title", "Plug in the phone", "--step", "Plug it in")
    add(title="Third?")
    code, out, _ = run("ok", "a1", "A2", "--lane", "api")      # lower case accepted
    assert code == 0 and out == "Approved: A1. Skipped (no suggested answer): A2.\n"
    code, out, _ = run("ok", "all", "--lane", "api")
    assert out == "Approved: A3. Skipped (no suggested answer): A2.\n"
    a = {x["ask"]: x for x in s.read_state("api")["asks"]}
    assert a["A1"]["answer"] == "Yes" and a["A1"]["answered_via"] == "ok" and a["A2"]["status"] == "open"


def test_G6_2_show_every_field_and_event_oldest_first():
    add("--detail", "the long story")
    run("ok", "A1", "--lane", "api")
    code, out, _ = run("show", "A1", "--lane", "api")
    assert code == 0 and "title: Merge #651 now?" in out and "detail: the long story" in out
    ev_lines = out.split("events:\n")[1].splitlines()
    assert [ln.split()[3] for ln in ev_lines] == ["asked", "answered"] and "ET" in ev_lines[0]
    assert len(js("show", "A1", "--lane", "api")["data"]["events"]) == 2


def test_G6_2_lane_text_uses_the_session_name(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SID)
    L.resolve(SID, "API Server")
    assert run("lane")[1] == "api-server (API Server)\n"


def test_G6_2_export_jsonl_and_csv_all_lanes():
    add()
    add(lane="web")
    run("done", "A1", "--lane", "api")
    code, out, _ = run("export", "--lane", "api")
    lines = out.splitlines()
    assert code == 0 and [json.loads(x)["type"] for x in lines] == ["asked", "done"]
    code, out, _ = run("export", "--format", "csv", "--all-lanes")
    rows = list(csv.DictReader(io.StringIO(out)))
    assert [(r["lane"], r["ask"], r["status"]) for r in rows] == [("api", "A1", "done"), ("web", "A1", "open")]


def test_G6_2_version_text(tmp_home, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_home.parent / "home"))
    code, out, _ = run("version")
    assert code == 0 and out.startswith(cli.__version__ + " (installed none, hooks gen ")
    (tmp_home / "update").mkdir(parents=True)
    (tmp_home / "update" / "pin").write_text("0.1.0\n")
    assert "pinned 0.1.0" in run("version")[1]


def test_G6_2_no_unlisted_commands_or_flags():
    names = set(cli.COMMANDS)
    plan = {"add", "update", "answer", "ok", "no", "done", "withdraw", "reopen", "list", "board", "show",
            "status", "badge", "lane", "sync", "inbox", "hook", "hub", "setup", "doctor", "export", "mcp",
            "version"}
    assert names <= plan
    p = cli.parser()
    sub = next(a for a in p._actions if isinstance(a, cli.argparse._SubParsersAction))
    for name, sp in sub.choices.items():
        flags = {o for a in sp._actions for o in a.option_strings} - {"-h", "--help"}
        assert {"--lane", "--json"} <= flags, name


# ---------------------------------------------------------------- G6.3

def test_G6_3_exit_codes():
    assert run("add", "--lane", "api")[0] == 2                                   # bad usage
    assert run("frobnicate")[0] == 2
    assert run("show", "B7", "--lane", "api")[0] == 2
    assert run("add", "--title", "x", "--suggested", "y")[0] == 3                # lane unknown
    assert run("done", "A1", "--lane", "api")[0] == 4                            # not found
    add()
    run("done", "A1", "--lane", "api")
    code, _, err = run("done", "A1", "--lane", "api")                            # transition
    assert code == 5 and "A1 is done" in err
    code, _, err = run("withdraw", "A1", "--lane", "api", "--reason", "x")
    assert code == 5 and "done" in err
    assert run("add", "--lane", "api", "--title", "x" * 121, "--suggested", "y")[0] == 6   # invalid field
    assert run("add", "--lane", "api", "--title", "x", "--suggested", "y", "--deadline", "soon")[0] == 6
    with s.LaneLock("api", timeout=0.1):                                          # busy after the 3 s wait
        assert run("add", "--lane", "api", "--title", "x", "--suggested", "y")[0] == 7


def test_G6_3_answer_rules_follow_G1_11():
    add()
    run("answer", "A1", "--lane", "api", "--answer", "agent wrote", "--by", "agent")
    assert run("answer", "A1", "--lane", "api", "--answer", "again", "--by", "agent")[0] == 5
    assert run("ok", "A1", "--lane", "api")[0] == 0                              # operator over agent
    assert run("no", "A1", "--lane", "api")[0] == 5                              # operator over operator


def test_G6_3_one_bad_id_writes_nothing():
    add()
    before = s.log_size("api")
    assert run("no", "A1", "A9", "--lane", "api")[0] == 4
    assert s.log_size("api") == before


def test_G6_3_unexpected_error_is_one_line_exit_1(monkeypatch):
    def boom(args):
        raise RuntimeError("kaput")
    monkeypatch.setitem(cli.COMMANDS, "lane", boom)
    code, out, err = run("lane", "--lane", "api")
    assert code == 1 and out == "" and err == "pitboard: unexpected error: RuntimeError: kaput\n"


# ---------------------------------------------------------------- G6.4 to G6.8

def test_G6_4_first_word_is_the_id():
    add()
    code, out, _ = add(title="Again?")
    assert out.split(" ")[0] == "A2"


def test_G6_5_hand_needs_steps_question_needs_suggested():
    code, _, err = run("add", "--lane", "api", "--kind", "hand", "--title", "Plug it in")
    assert code == 6 and err.count("\n") == 1 and "--step" in err
    for kind in ("question", "decision"):
        code, _, err = run("add", "--lane", "api", "--kind", kind, "--title", "Go?")
        assert code == 6 and "--suggested" in err
    assert run("add", "--lane", "api", "--kind", "permission", "--title", "Run rm?")[0] == 0
    assert run("add", "--lane", "api", "--kind", "hand", "--title", "Plug", "--step", "a", "--step", "b")[0] == 0
    assert s.all_asks("api")  # nothing refused was written
    assert len(s.read_log("api")[0]) == 2


def test_G6_6_write_commands_rebuild_the_cache():
    add()
    assert s.read_json(s.state_path("api"))["open"] == 1
    run("done", "A1", "--lane", "api")
    st = s.read_json(s.state_path("api"))
    assert st["open"] == 0 and st["log_bytes"] == s.log_size("api")


def test_G6_7_add_fills_where(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TMUX_PANE", "%7")
    monkeypatch.setattr(cli, "_tmux", lambda pane, fmt: {"#{session_name}": "lanes",
                                                          "#{window_name}": "bad name!"}[fmt])
    add()
    w = s.read_log("api")[0][0]["data"]["where"]
    assert w["cwd"] == str(tmp_path) and w["tmux_pane"] == "%7" and w["tmux_session"] == "lanes"
    assert "tmux_window" not in w and c.WHERE_TOKEN.match(w["host"])


def test_G6_7_tmux_lookup_has_a_1s_limit(monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw, cmd=cmd)
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli._tmux("%1", "#{session_name}") is None
    assert seen["timeout"] == 1 and seen["cmd"][:5] == ["tmux", "display", "-p", "-t", "%1"]


def test_G6_8_text_fits_in_100_columns():
    add("--detail", "word " * 300)
    code, out, _ = run("show", "A1", "--lane", "api")
    assert code == 0 and max(len(ln) for ln in out.splitlines()) <= 100
    assert any(ln.endswith("…") for ln in out.splitlines())
    assert cli.fit("x" * 150) == "x" * 99 + "…" and cli.fit("short") == "short"
