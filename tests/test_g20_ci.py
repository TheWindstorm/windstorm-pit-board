"""G20.6, G20.8: the CI workflow's triggers and rules (and the G9.5 gate step)."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(ROOT, ".github", "workflows")
RUNNER = re.compile(r"^(ubuntu|macos|windows)-[0-9]+(\.[0-9]+)?$")       # G20.8 (plan 1.29, P22): an image, never latest


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


def runner_labels(text):
    """Every runner label a workflow names: runs-on directly, the matrix list it names, and a matrix include's os."""
    out = []
    for value in re.findall(r"runs-on:\s*(.+)", text):
        value = value.strip()
        if value.startswith("${{ matrix."):
            key = value[len("${{ matrix."):].rstrip("} ").strip()
            m = re.search(rf"^\s+{key}:\s*\[(.*?)\]", text, re.M)
            out += [x.strip().strip("'\"") for x in m.group(1).split(",")] if m else ["<no matrix " + key + ">"]
        else:
            out.append(value.strip("'\""))
    out += [x.strip("'\"") for x in re.findall(r"^\s*-?\s*os:\s*([^\s\[#]+)\s*$", text, re.M)]
    return out


def test_G20_8_standard_github_hosted_runners_only():
    for name, text in workflows():
        labels = runner_labels(text)
        assert labels, name
        for label in labels:
            assert RUNNER.match(label), (name, label)


def test_G20_8_every_job_names_its_runner_image_never_latest():
    """P22 (plan 1.29): ubuntu-latest moved to a new Ubuntu under the matrix and setup-python had no 3.9 for it."""
    for bad in ("runs-on: ubuntu-latest\n", "runs-on: ${{ matrix.os }}\n    strategy:\n      matrix:\n        os: [ubuntu-24.04, macos-latest]\n",
                "runs-on: ${{ matrix.os }}\n        include:\n          - os: windows-latest\n", "runs-on: ubuntu-24.04-4-cores\n"):
        assert [x for x in runner_labels(bad) if not RUNNER.match(x)], bad
    assert all(RUNNER.match(x) for x in runner_labels("runs-on: ${{ matrix.os }}\n      matrix:\n        os: [ubuntu-24.04, macos-26]\n"))


def test_G20_6_python_and_os_matrix_and_triggers():
    text = dict(workflows())["tests.yml"]
    assert re.search(r'python: \["3\.9", "3\.10", "3\.13"\]', text)          # 3.9: the floor (G21.15, plan 1.26)
    assert re.search(r"os: \[ubuntu-24\.04\]", text)
    assert 'on:\n  push:\n    branches: [main, "release-*"]\n  pull_request:\n' in text   # each commit's checks once


def _job(text, name):
    m = re.search(rf"^  {name}:\n((?:    .*\n|\n)*)", text, re.M)
    assert m, f"no job {name}"
    return m.group(1)


def test_G20_6_a_pull_request_runs_one_mac_job_and_main_runs_them_all():
    """Family rule 17 (2026-11-23): GitHub gives the account a few Mac runners for all its repositories together, and
    one afternoon 34 runs sat queued with none running. A pull request runs one Mac job, the floor's Python; main and
    release-* run every Python. A newer push to a pull request cancels its older runs; a push never is."""
    import json
    from pitboard import launch
    text = dict(workflows())["tests.yml"]
    mac = [j for j in re.findall(r"^  ([a-z-]+):\n", text, re.M) if re.search(r"runs-on: macos", _job(text, j))]
    assert mac == ["test-mac"], mac
    job = _job(text, "test-mac")
    m = re.search(r"python: \$\{\{ fromJSON\(github\.event_name == 'pull_request' && '(.*?)' \|\| '(.*?)'\) \}\}", job)
    assert m, "the Mac job's Python list must depend on the event"
    assert json.loads(m.group(1)) == ["{}.{}".format(*launch.FLOOR)]           # a pull request: the floor only
    assert json.loads(m.group(2)) == ["3.9", "3.10", "3.13"]                    # main and release-*: all
    assert _job(text, "test")[_job(text, "test").index("    steps:"):] == job[job.index("    steps:"):]   # same steps
    assert ("concurrency:\n  group: ${{ github.event_name == 'pull_request' && format('{0}-pr-{1}', github.workflow, "
            "github.event.pull_request.number) || format('{0}-push-{1}', github.workflow, github.sha) }}\n"
            "  cancel-in-progress: ${{ github.event_name == 'pull_request' }}\n") in text


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
    steps = list(re.finditer(r"^( +)- run: python -m pytest (.*)\n((?:\1  .*\n)*)", text, re.M))
    assert len(steps) == 2, "one pytest step in each test job"
    longest = max(request.session.items, key=lambda i: len(i.nodeid)).nodeid
    for step in steps:
        assert "-o console_output_style=classic" in step.group(2), "the pytest step must use the classic style"
        m = re.search(r'^\s+COLUMNS: "(\d+)"$', step.group(3), re.M)
        assert m, "the pytest step must set COLUMNS"
        room = int(m.group(1)) - 200                   # a reason, the outcome word and the indent
        assert len("tests/" + longest) <= room, f"a test ID of {len(longest)} characters leaves no room for a reason"


def test_G9_5_ci_runs_the_skill_format_gate():
    text = dict(workflows())["tests.yml"]
    assert "gh skill publish --dry-run" in text
