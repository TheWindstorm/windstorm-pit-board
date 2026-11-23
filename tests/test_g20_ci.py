"""G20.6, G20.8: the CI workflow's triggers and rules (and the G9.5 gate step)."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(ROOT, ".github", "workflows")
RUNNER = re.compile(r"^(ubuntu|macos|windows)-(latest|[0-9]+(\.[0-9]+)?)$")


def workflows():
    for n in sorted(os.listdir(WF)):
        if n.endswith((".yml", ".yaml")):
            with open(os.path.join(WF, n), encoding="utf-8") as f:
                yield n, f.read()


def test_G20_8_read_only_no_secrets_no_pull_request_target():
    for name, text in workflows():
        assert re.search(r"^permissions:\n  contents: read\n", text, re.M), name
        assert "secrets." not in text, name
        assert "pull_request_target" not in text, name


def test_G20_8_standard_github_hosted_runners_only():
    for name, text in workflows():
        for value in re.findall(r"runs-on:\s*(.+)", text):
            value = value.strip()
            if value.startswith("${{ matrix."):
                key = value[len("${{ matrix."):].rstrip("} ").strip()
                m = re.search(rf"^\s+{key}:\s*\[(.*?)\]", text, re.M)
                assert m, (name, value)
                labels = [x.strip().strip("'\"") for x in m.group(1).split(",")]
            else:
                labels = [value.strip("'\"")]
            for label in labels:
                assert RUNNER.match(label), (name, label)


def test_G20_6_python_and_os_matrix_and_triggers():
    text = dict(workflows())["tests.yml"]
    assert re.search(r'python: \["3\.9", "3\.10", "3\.13"\]', text)          # 3.9: the floor (G21.15, plan 1.26)
    assert re.search(r"os: \[ubuntu-latest, macos-latest\]", text)
    assert "on:\n  push:\n    branches: [main]\n  pull_request:\n" in text


def test_G20_6_ci_log_names_every_test_and_its_outcome():
    """Plans 1.21 and 1.22: a count cannot show that a given test ran in a job. -v gives each test its own line;
    -q would cancel it, and -rA alone folds skips into one line without names."""
    text = dict(workflows())["tests.yml"]
    runs = re.findall(r"^\s+- run: (python -m pytest .*)$", text, re.M)
    assert runs, "no pytest run step"
    for r in runs:
        flags = r.split()
        assert "-v" in flags or "--verbose" in flags, r
        assert not any(f in ("-q", "--quiet") or re.fullmatch(r"-[a-z]*q[a-z]*", f) for f in flags), r


def test_G20_6_ci_has_room_for_every_skip_reason(request):
    """pytest drops a skip's reason when its test's line would not fit the terminal; CI's is 80 columns, so the
    step sets COLUMNS and the classic style (no progress column to pad to). Every collected test's ID, with room
    for a reason, must fit."""
    text = dict(workflows())["tests.yml"]
    step = re.search(r"^( +)- run: python -m pytest (.*)\n((?:\1  .*\n)*)", text, re.M)
    assert step and "-o console_output_style=classic" in step.group(2), "the pytest step must use the classic style"
    m = re.search(r'^\s+COLUMNS: "(\d+)"$', step.group(3), re.M)
    assert m, "the pytest step must set COLUMNS"
    room = int(m.group(1)) - 200                       # a reason, the outcome word and the indent
    longest = max(request.session.items, key=lambda i: len(i.nodeid)).nodeid
    assert len("tests/" + longest) <= room, f"a test ID of {len(longest)} characters leaves no room for a reason"


def test_G9_5_ci_runs_the_skill_format_gate():
    text = dict(workflows())["tests.yml"]
    assert "gh skill publish --dry-run" in text
