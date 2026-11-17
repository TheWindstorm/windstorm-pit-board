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
    assert re.search(r'python: \["3\.10", "3\.13"\]', text)
    assert re.search(r"os: \[ubuntu-latest, macos-latest\]", text)
    assert "on:\n  push:\n    branches: [main]\n  pull_request:\n" in text


def test_G9_5_ci_runs_the_skill_format_gate():
    text = dict(workflows())["tests.yml"]
    assert "gh skill publish --dry-run" in text
