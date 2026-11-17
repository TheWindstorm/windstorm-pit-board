"""G9: the skill files, checked with the standard library alone (G9.4 points 1 to 4, G9.5)."""
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")
NAMES = sorted(d for d in os.listdir(SKILLS) if os.path.isfile(os.path.join(SKILLS, d, "SKILL.md")))
KEY = re.compile(r"^([a-z][a-z-]*):(?: (.*))?$")
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def read(name):
    with open(os.path.join(SKILLS, name, "SKILL.md"), encoding="utf-8") as f:
        return f.read()


def frontmatter(text):
    """A strict parse: '---' lines around 'key: value' lines; a double-quoted value is JSON."""
    lines = text.split("\n")
    assert lines[0] == "---", "SKILL.md starts with ---"
    end = lines.index("---", 1)
    out = {}
    for ln in lines[1:end]:
        m = KEY.match(ln)
        assert m, f"not a plain 'key: value' line: {ln!r}"
        k, v = m.group(1), m.group(2) or ""
        assert k not in out, f"duplicate key {k}"
        if v.startswith('"'):
            v = json.loads(v)              # a double-quoted YAML scalar with \" and \\ escapes
            assert isinstance(v, str)
        out[k] = v
    return out, "\n".join(lines[end + 1:])


def test_G9_4_the_skills_are_pit_board_and_board():
    assert NAMES == ["board", "pit-board"]


@pytest.mark.parametrize("name", NAMES)
def test_G9_4_format(name):
    text = read(name)
    fm, _ = frontmatter(text)
    assert fm["name"] == name and NAME.match(name)                                         # point 1
    raw = next(ln for ln in text.split("\n") if ln.startswith("description: "))
    assert raw.startswith('description: "') and raw.endswith('"')                         # point 2
    assert 0 < len(fm["description"]) <= 1024
    assert text.count("\n") < 500                                                          # point 3
    assert not any(k.startswith("metadata") for k in fm)                                   # point 4
    assert "allowed-tools" not in fm or isinstance(fm["allowed-tools"], str)


def test_G9_1_pit_board_body_is_appendix_A5_word_for_word():
    with open(os.path.join(ROOT, "DNA-STRAND-MASTER-PLAN.md"), encoding="utf-8") as f:
        plan = f.read()
    a5 = plan[plan.index("### A.5 The skill body"):]
    body = a5[a5.index("```markdown\n") + len("```markdown\n"):]
    body = body[: body.index("\n```\n")] + "\n"
    _, skill_body = frontmatter(read("pit-board"))
    assert skill_body == "\n" + body


def test_G9_1_pit_board_triggers():
    d = frontmatter(read("pit-board"))[0]["description"].lower()
    for word in ("decision", "approval", "login", "payment", "signature", "account", "pit board", '"pb"',
                 "asks", "action items", "what's waiting on me"):
        assert word in d, word
    assert "grant" not in read("pit-board").lower()           # fixed file: "the operator" (G9.1)


def test_G9_2_skill_names_the_stable_launcher_fallback():
    assert "If `command -v pitboard` finds nothing, use `~/.pitboard/bin/pitboard`" in read("pit-board")
    assert "~/.pitboard/bin/pitboard" in read("board")


def test_G9_3_board_skill_runs_the_plain_board_and_shows_it_as_is():
    _, body = frontmatter(read("board"))
    assert "`pitboard board --plain`" in body and "`pitboard board --all --plain`" in body
    assert "$ARGUMENTS" in body and "code block" in body and "no comment before or after" in body
