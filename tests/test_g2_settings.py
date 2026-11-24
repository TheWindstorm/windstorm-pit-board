"""P38 (the maintainer's ruling): every setting Pit Board reads is named where a person reads it. Each environment
read in the code is in one of three groups: the README's list of settings a person may set, the facts Claude Code
and the terminal give, or the launcher's and the status line wrapper's own markers to the code they start,
which they set themselves."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = {"CLAUDE_CODE_SESSION_ID", "CLAUDE_ENV_FILE", "CLAUDE_PLUGIN_ROOT", "TMUX_PANE", "NO_COLOR", "COLUMNS", "TZ"}
OWN = {"PITBOARD_LAUNCH_STEP", "PITBOARD_LAUNCH_UNREAD", "PITBOARD_LAUNCH_NS",   # the launcher's, to its own code
       "PITBOARD_WRAPPER_SID", "PITBOARD_WRAPPER_NAME"}                          # P54: the wrapper's, to status
READ = re.compile(r"""(?:environ(?:\.get)?|env\.get|getenv)\s*[\[(]\s*["']([A-Z][A-Z0-9_]*)["']""")
TOKEN = re.compile(r"""["']((?:PITBOARD|CLAUDE)_[A-Z0-9_]+)["']""")      # quoted: a name, not a constant
SHELL = re.compile(r"\$\{?((?:PITBOARD|CLAUDE)_[A-Z0-9_]+)")
IN_ENV = re.compile(r"""["']([A-Z][A-Z0-9_]*)["']\s+(?:not\s+)?in\s+(?:os\.)?(?:environ|env)\b""")


def _text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def code_reads(texts):
    """Every name the code reads from the environment, and every PITBOARD_/CLAUDE_ name it writes as a string (a
    read through a table, such as the config overrides, is found by its name; a Python constant is not a name)."""
    names = set()
    for t in texts:
        names |= set(READ.findall(t)) | set(TOKEN.findall(t)) | set(SHELL.findall(t)) | set(IN_ENV.findall(t))
    return names


def readme_settings(readme):
    part = readme.split("## Settings\n", 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"^- `([A-Z][A-Z0-9_]*)`:", part, re.M))


def problems(texts, readme):
    listed = readme_settings(readme)
    return sorted(n for n in code_reads(texts) if n not in listed | HOST | OWN)


def _code():
    pkg = os.path.join(ROOT, "pitboard")
    return ([_text("pitboard", n) for n in sorted(os.listdir(pkg)) if n.endswith(".py")]
            + [_text("bin", "pitboard"), _text("hooks", "hooks.json")])


def test_G2_10_every_setting_the_code_reads_is_named_for_a_person():
    readme = _text("README.md")
    assert readme_settings(readme) == {"PITBOARD_HOME", "PITBOARD_MACHINE", "PITBOARD_TZ", "PITBOARD_SELF_UPDATE",
                                       "PITBOARD_LANE"}
    assert problems(_code(), readme) == []
    assert "PITBOARD_HUB_URL" not in code_reads(_code())                    # no hub, so no hub setting


def test_G2_10_a_read_in_no_group_fails():
    readme = _text("README.md")
    for extra in ['os.environ.get("PITBOARD_FAST_WAITS")', 'x = os.environ["SHORT_LOCKS"]',
                  'ENV = {"PITBOARD_HUB_URL": "hub_url"}', 'R="${PITBOARD_FAKE_NOW}"', 'if "SKIP_CHECKS" in env:']:
        assert problems(_code() + [extra], readme), extra
    assert problems(_code(), readme.replace("- `PITBOARD_LANE`:", "- PITBOARD_LANE:")) == ["PITBOARD_LANE"]
