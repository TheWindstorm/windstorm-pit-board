"""G7 (Milestone 1 part): hooks.json, session-start, user-prompt-submit, stop, cwd-changed; G16.4; G21.6.

Hook inputs are the real ones recorded in the Part 7 checks (tests/fixtures/hooks/<hook>/)."""
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from pitboard import __version__, cli, contract as c, hooks as H, lane as L, render as R, store as s, timefmt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "hooks")
SID = "00000000-0000-4000-8000-000000000001"
NY = timefmt.zone("America/New_York")


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("PITBOARD_HOME", str(tmp_path / "pb"))
    monkeypatch.setenv("PITBOARD_MACHINE", "studio-1")
    monkeypatch.setenv("PITBOARD_TZ", "America/New_York")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(tmp_path / "env.sh"))
    for k in ("PITBOARD_LANE", "CLAUDE_CODE_SESSION_ID", "TMUX_PANE", "NO_COLOR", "COLUMNS"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path


def fixture(hook, variant, **change):
    path = os.path.join(FIX, hook, variant + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
    else:  # the Part 7 fixtures arrive in their own pull request; a minimal stand-in keeps this file runnable
        obj = {"session_id": SID, "hook_event_name": hook, "cwd": "/home/user/project",
               "transcript_path": "/home/user/.claude/projects/x/" + SID + ".jsonl"}
    obj["session_id"] = SID
    obj.update(change)
    return obj


def hook(name, obj):
    out, err = io.StringIO(), io.StringIO()
    stdin = io.StringIO(json.dumps(obj) if not isinstance(obj, str) else obj)
    real = cli.sys.stdin
    cli.sys.stdin = stdin
    try:
        code = cli.main(["hook", name], stdout=out, stderr=err)
    finally:
        cli.sys.stdin = real
    assert code == 0 and err.getvalue() == ""
    text = out.getvalue()
    return json.loads(text) if text else None


def transcript(tmp, name):
    p = tmp / "t.jsonl"
    p.write_text(json.dumps({"type": "custom-title", "customTitle": name, "sessionId": SID}) + "\n")
    return str(p)


def add(key, title="Merge #651 now?", **kw):
    args = ["add", "--lane", key, "--title", title]
    if kw.get("kind") != "hand":
        args += ["--suggested", kw.pop("suggested", "merge now")]
    for k, v in kw.items():
        args += [f"--{k}", v] if not isinstance(v, list) else sum(([f"--{k}", x] for x in v), [])
    code = cli.main(args, stdout=io.StringIO(), stderr=io.StringIO())
    assert code == 0


def start(home, name="API Server"):
    # C3: session_title holds the --name//rename name (G3.2 step 1); the transcript says the same
    return hook("session-start", fixture("session-start", "startup", transcript_path=transcript(home, name),
                                         session_title=name))


def ctx_of(out):
    return out["hookSpecificOutput"]["additionalContext"]


# ---------------------------------------------------------------- G7.0, G21.6, G21.1

HOOK_TABLE = {"session-start": "SessionStart", "user-prompt-submit": "UserPromptSubmit", "stop": "Stop",
              "cwd-changed": "CwdChanged"}


def test_G7_0_every_command_has_the_exact_shape():
    with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as f:
        h = json.load(f)["hooks"]
    assert set(h) == set(HOOK_TABLE.values())
    for name, event in HOOK_TABLE.items():
        (entry,) = h[event]
        (cmd,) = entry["hooks"]
        assert cmd["type"] == "command" and "matcher" not in entry
        assert cmd["command"] == ('R="${CLAUDE_PLUGIN_ROOT}"; [ -f "$R/pitboard/launch.py" ] || exit 0; P=python3; '
                                  'python3 -I -c pass </dev/null >/dev/null 2>&1 || P=python; '
                                  'exec "$P" -I "$R/pitboard/launch.py" hook ' + name)
        assert cmd["timeout"] == (10 if name == "session-start" else 5)


def test_G7_0_missing_plugin_folder_does_nothing(tmp_path):
    with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as f:
        cmd = json.load(f)["hooks"]["Stop"][0]["hooks"][0]["command"]
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(tmp_path / "gone"))
    r = subprocess.run(["sh", "-c", cmd], input="{}", capture_output=True, text=True, env=env, timeout=30)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


def test_G7_0_command_runs_through_the_launcher(home):
    with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as f:
        cmd = json.load(f)["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=ROOT, HOME=str(home / "h"))
    r = subprocess.run(["sh", "-c", cmd], input=json.dumps(fixture("session-start", "startup")),
                       capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0 and r.stderr == ""
    assert json.loads(r.stdout)["hookSpecificOutput"]["hookEventName"] == "SessionStart"


# The hooks.json each generation was released with. Changing hooks.json means raising
# hooks/generation.json and adding its hash here (G21.6).
GENERATIONS = {1: "d0d306ca49c483878632c4a25b0edad680cb44af0fc85447bad33169f175fdcc"}


def test_G21_6_hooks_change_only_with_a_new_generation():
    with open(os.path.join(ROOT, "hooks", "generation.json"), encoding="utf-8") as f:
        gen = json.load(f)
    with open(os.path.join(ROOT, "hooks", "hooks.json"), "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    assert isinstance(gen, int) and gen == max(GENERATIONS)
    assert GENERATIONS[gen] == digest, "hooks/hooks.json changed: raise hooks/generation.json (G21.6)"


def test_G21_1_plugin_version_equals_the_package_version():
    with open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
        man = json.load(f)
    assert man["name"] == "windstorm-pit-board" and man["version"] == __version__
    assert re.match(r"^\d+\.\d+\.\d+$", man["version"])
    assert "statusLine" not in man                          # a plugin cannot set it (Part 7)


# ---------------------------------------------------------------- G7.1, G7.7

def test_G7_1_resolves_lane_writes_env_line_once_and_reminds(home):
    out = start(home)
    row = L.read_map()[SID]
    assert row["lane"] == "api-server" and row["lane_name"] == "API Server"
    assert (home / "env.sh").read_text() == "export PITBOARD_LANE=api-server\n"
    assert ctx_of(out).startswith('Pit Board: you are lane "API Server" (key api-server) on studio-1.')
    start(home)                                             # resume, compact: the line is not doubled
    assert (home / "env.sh").read_text().count("PITBOARD_LANE") == 1


def test_G7_1_never_overwrites_other_plugins_lines(home):
    (home / "env.sh").write_text("export OTHER=1\n")
    start(home)
    assert (home / "env.sh").read_text() == "export OTHER=1\nexport PITBOARD_LANE=api-server\n"


@pytest.mark.parametrize("source", ["startup", "resume", "compact", "clear", "fork"])
def test_G7_1_every_source(home, source):
    obj = fixture("session-start", source, transcript_path=transcript(home, "API Server"), source=source,
                  session_title="API Server")
    assert "api-server" in ctx_of(hook("session-start", obj))


def test_G7_7_reminder_with_and_without_asks(home):
    out = ctx_of(start(home))
    assert out.splitlines() == ['Pit Board: you are lane "API Server" (key api-server) on studio-1.',
                                "Rules: record every new ask with `pitboard add` before you ask it, "
                                "and start the question with its ID. That includes an ask only the operator can "
                                "answer that you send to another agent (a coordinator, a reviewer) or a shared "
                                "board instead of the chat."]
    add("api-server")
    add("api-server", title="create a Stripe account", kind="hand", step=["Go to stripe.com"],
        deadline="2026-12-31 17:00")
    lines = ctx_of(start(home)).splitlines()
    assert lines[0].endswith("on studio-1. 2 asks wait on the operator:")
    assert "- A1 [RED, 0m] Merge #651 now? Suggested: merge now." in lines
    assert any(ln.startswith("- A2 [BLUE, 0m] YOUR HAND: create a Stripe account. Due Dec 31 5:00 PM ET.")
               for ln in lines)
    assert lines[-1].startswith("If the operator has answered one, run `pitboard answer <ID> --by operator")


def test_G7_7_an_ask_sent_to_another_agent_or_a_board_is_recorded_too():
    """P13 (plan 1.24): the reminder and the skill name an operator's ask that leaves the chat. Its proof is P4's
    (a real ask recorded unprompted on two days); this test holds the words, with and without asks."""
    now = datetime(2026, 11, 23, 6, 0, tzinfo=timezone.utc)
    want = ("That includes an ask only Dana can answer that you send to another agent (a coordinator, a reviewer) "
            "or a shared board instead of the chat.")
    ask = {"uid": "0" * 32, "ask": "A1", "status": "open", "kind": "question", "severity": "blocking",
           "title": "Post this under Dana's name?", "asked_at": c.ts_of(now)}
    for asks in ([], [ask]):
        text = R.reminder_text("k", "Lane", "m", asks, NY, now, cfg={"operator_name": "Dana"})
        rules = [ln for ln in text.splitlines() if ln.startswith("Rules:")]
        assert len(rules) == 1 and rules[0].endswith(want), text
    with open(os.path.join(ROOT, "skills", "pit-board", "SKILL.md"), encoding="utf-8") as f:
        skill = f.read()
    assert "questions to other agents that they can answer themselves" in skill
    assert "Answer under A12, or say 'not mine to answer' under A12." in skill
    assert "`pitboard answer A12 --by agent --answer \"<who>: <their answer>\"`" in skill


def test_G7_7_operator_name_limit_and_3000_chars():
    now = datetime(2026, 11, 17, 19, 0, tzinfo=timezone.utc)
    asks = [{"uid": f"{n:032x}", "ask": f"A{n}", "status": "open", "kind": "question", "severity": "blocking",
             "title": "x" * 110, "suggested": "y" * 400, "asked_at": c.ts_of(now - timedelta(hours=1))}
            for n in range(1, 41)]
    text = R.reminder_text("k", "Lane", "m", asks, NY, now, cfg={"operator_name": "Grant",
                                                                    "reminder_max_items": 20})
    assert len(text) < 3000 and "wait on Grant:" in text and "If Grant has answered one" in text
    assert re.search(r"\(\+\d+ more: pitboard list\)", text)
    few = R.reminder_text("k", "Lane", "m", asks[:5], NY, now, cfg={"reminder_max_items": 3})
    assert "(+2 more: pitboard list)" in few and few.count("\n- A") == 3


def test_G7_7_page_answered_asks_are_listed():
    now = datetime(2026, 11, 17, 19, 0, tzinfo=timezone.utc)
    a = {"uid": "a" * 32, "ask": "A12", "status": "answered", "answered_via": "page", "answer": "ship it",
         "asked_at": c.ts_of(now)}
    text = R.reminder_text("k", "Lane", "m", [a], NY, now)
    assert 'Answered on the master list, not done yet: A12 → "ship it"' in text


# ---------------------------------------------------------------- G7.2

def prompt(text):
    return hook("user-prompt-submit", fixture("user-prompt-submit", "basic", prompt=text))


@pytest.mark.parametrize("text", ["pb", " PB ", "pb all", "/board", "/Board All"])
def test_G7_2_step1_board_blocks_with_the_board(home, text):
    start(home)
    add("api-server")
    out = prompt(text)
    assert out["decision"] == "block"
    assert out["hookSpecificOutput"] == {"hookEventName": "UserPromptSubmit", "suppressOriginalPrompt": True}
    assert out["reason"].startswith("PIT BOARD · API Server · " + ("history" if "all" in text.lower() else "1 open"))
    assert not (home / "pb" / "state" / "api-server.activity").exists()   # no model turn: not busy


def test_G7_2_step2_approval_runs_ok_and_tells_the_agent(home):
    start(home)
    add("api-server")
    add("api-server", title="Keep it?", suggested="keep")
    add("api-server", title="Plug in", kind="hand", step=["plug"])
    out = prompt("OK A1, A2.")
    assert ctx_of(out) == ('Pit Board: the operator approved A1: "merge now"; A2: "keep". Carry them out now. '
                           "When each is finished, run: pitboard done <ID>.")
    st = {a["ask"]: a for a in s.read_state("api-server")["asks"]}
    assert st["A1"]["answered_by"] == "operator" and st["A1"]["answered_via"] == "ok"
    assert prompt("approve all") is None                    # only A3 is open, and it has no suggested answer
    assert {a["ask"]: a["status"] for a in s.read_state("api-server")["asks"]}["A3"] == "open"


@pytest.mark.parametrize("text", ["ok", "ok A", "okay A1", "ok A1 please do it", "ok A1 and A2"])
def test_G7_2_step2_only_whole_prompt_matches(home, text):
    start(home)
    add("api-server")
    out = prompt(text)
    assert out is None or "approved" not in ctx_of(out)
    assert s.read_state("api-server")["asks"][0]["status"] == "open"


def test_G7_2_step3_decline(home):
    start(home)
    add("api-server")
    out = prompt("no A1")
    assert ctx_of(out) == ("Pit Board: the operator declined A1. Do not do them. "
                           "Ask what to do instead only if you are blocked.")
    a = s.read_state("api-server")["asks"][0]
    assert (a["answer"], a["answered_via"]) == ("No.", "no")


def test_G7_2_step4_mentions_only_open_asks(home):
    start(home)
    add("api-server")
    add("api-server", title="Second?")
    cli.main(["done", "A2", "--lane", "api-server"], stdout=io.StringIO(), stderr=io.StringIO())
    out = prompt("About A1 and A2 and A9: yes to A1")
    assert ctx_of(out).startswith("Pit Board: this message answers or mentions A1. If it answers one, run: "
                                  "pitboard answer <ID> --by operator")
    assert prompt("nothing here") is None


def test_G7_2_step5_closes_this_sessions_stale_prompts(home):
    start(home)
    for src, sid in (("question-box", SID), ("permission", SID), ("question-box", "other-session"),
                     ("agent", SID)):
        s.append("api-server", lambda v, src=src, sid=sid: c.make_event(
            "asked", uid=c.new_id(), ask=v.next_ask_id(), lane="api-server", lane_name="API Server",
            machine="studio-1", session_id=sid, by="hook",
            data={"kind": "decision", "severity": "blocking", "title": "Q?", "suggested": "a", "source": src}))
    prompt("carry on")
    st = {a["ask"]: a["status"] for a in s.all_asks("api-server").values()}
    assert st == {"A1": "withdrawn", "A2": "withdrawn", "A3": "open", "A4": "open"}
    w = [e for e in s.read_log("api-server")[0] if e["type"] == "withdrawn"]
    assert {e["data"]["reason"] for e in w} == {"prompt closed"} and {e["by"] for e in w} == {"hook"}


def test_G16_4_busy_on_prompt_idle_on_stop(home):
    start(home)
    prompt("go on")
    act = home / "pb" / "state" / "api-server.activity"
    word, ts = act.read_text().split()
    assert word == "busy" and c.TS.match(ts)
    assert hook("stop", fixture("stop", "basic")) is None
    assert act.read_text().split()[0] == "idle"


def test_G7_2_busy_lane_still_marks_busy_and_logs(home):
    start(home)
    add("api-server")
    with s.LaneLock("api-server", timeout=0.1):
        out = prompt("ok A1")
    assert out is None
    assert s.read_state("api-server")["asks"][0]["status"] == "open"
    log = (home / "pb" / "logs" / "pitboard.log").read_text()
    assert "lane-busy user-prompt-submit api-server" in log


# ---------------------------------------------------------------- G7.8, INV6, logging

def test_G7_8_cwd_changed_adds_the_line_again(home):
    start(home)
    (home / "env.sh").write_text("")                        # Claude Code cleared it
    assert hook("cwd-changed", {"session_id": SID, "hook_event_name": "CwdChanged"}) is None
    assert (home / "env.sh").read_text() == "export PITBOARD_LANE=api-server\n"


@pytest.mark.parametrize("name,raw", [("session-start", "{not json"), ("user-prompt-submit", "[1]"),
                                      ("stop", ""), ("no-such-hook", "{}"), ("session-start", '{"session_id": 5}')])
def test_INV6_bad_input_exits_0_with_nothing(name, raw):
    assert hook(name, raw) is None


def test_INV6_handler_error_is_swallowed_and_logged(home, monkeypatch):
    monkeypatch.setattr(H, "render", None)                  # any attribute use now raises
    assert hook("session-start", fixture("session-start", "startup")) is None
    assert "session-start - error" in (home / "pb" / "logs" / "pitboard.log").read_text()


def test_G7_log_lines_hold_no_ask_text(home):
    start(home)
    add("api-server", title="Secret plan name?")
    prompt("ok A1")
    log = (home / "pb" / "logs" / "pitboard.log").read_text()
    assert "Secret plan" not in log and "merge now" not in log
    for ln in log.splitlines():
        assert re.match(r"^\d{4}-\d\d-\d\dT[\d:.]+Z [a-z-]+ \S+ .+$", ln)
