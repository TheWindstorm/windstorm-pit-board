"""Part 7: the recorded hook inputs (tests/fixtures/hooks) hold the facts the hooks rely on.
Results and sources: docs/CONTRACTS.md."""
import json
import os
import re

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures", "hooks")
NAMES = sorted(n[:-5] for n in os.listdir(FIX) if n.endswith(".json"))


def load(name):
    with open(os.path.join(FIX, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("name", NAMES)
def test_part7_fixture_is_a_hook_input_with_no_personal_data(name):
    obj = load(name)
    assert obj["hook_event_name"] == name.split("-")[0]
    text = json.dumps(obj)
    ids = set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text))
    assert all(i.startswith("00000000-0000-4000-8000-") for i in ids)
    for home in re.findall(r"/home/([^/\"]+)", text):
        assert home == "user"


def test_C1_every_session_start_source():
    assert {load(n)["source"] for n in NAMES if n.startswith("SessionStart-")} == \
        {"startup", "resume", "compact", "clear", "fork"}


def test_C3_session_title_is_the_rename_name():
    assert load("SessionStart-resume")["session_title"] == "Probe Renamed"


def test_C4_typed_slash_reaches_prompt_submit_then_expansion():
    assert load("UserPromptSubmit-slash")["prompt"] == "/board gamma"
    e = load("UserPromptExpansion-plugin-skill")
    assert e["command_name"].endswith(":board") and e["command_args"] == "gamma"


def test_C5_stop_has_last_assistant_message():
    s = load("Stop")
    assert isinstance(s["last_assistant_message"], str) and s["stop_hook_active"] is False


def test_C6_question_box_shapes():
    pre = load("PreToolUse-AskUserQuestion")
    q = pre["tool_input"]["questions"][0]
    assert {"question", "header", "options", "multiSelect"} <= set(q) and pre["tool_use_id"]
    post = load("PostToolUse-AskUserQuestion")
    assert post["tool_response"]["answers"] == {q["question"]: q["options"][0]["label"]}
    assert post["tool_use_id"] == pre["tool_use_id"]


def test_C7_permission_request_has_no_tool_use_id_and_also_fires_for_questions():
    for n in ("PermissionRequest-Bash", "PermissionRequest-AskUserQuestion"):
        p = load(n)
        assert "tool_use_id" not in p and p["tool_name"] and isinstance(p["tool_input"], dict)
    assert load("Notification-permission_prompt")["notification_type"] == "permission_prompt"
