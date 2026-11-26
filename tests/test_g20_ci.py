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


PLANTED = """import os, pwd, shutil, subprocess, sys
REAL = os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)
PROBE = "no-such-file-pit-board-guard-probe"           # a name that is never there: nothing real is read

def test_reads_the_real_pit_board_home():
    try:
        open(os.path.join(REAL, ".pitboard", PROBE))
    except OSError:
        pass

def test_reads_the_real_plugin_registry():
    try:
        open(os.path.join(REAL, ".claude", "plugins", PROBE))
    except OSError:
        pass

def test_reads_elsewhere_in_the_home():
    try:
        open(os.path.join(REAL, ".local", "bin", PROBE))
    except OSError:
        pass

def test_renames_into_the_home(tmp_path):
    (tmp_path / "x").write_text("x")
    try:                                    # a folder that is never there: the rename fails, the guard saw it
        os.rename(tmp_path / "x", os.path.join(REAL, PROBE + "-dir", "x"))
    except OSError:
        pass

def test_python_libraries_and_the_checkout_are_left_out():
    import site
    for d in (site.getusersitepackages(), os.path.dirname(os.path.abspath(__file__))):
        try:
            open(os.path.join(d, PROBE))
        except OSError:
            pass

def test_starts_a_child_with_no_home():
    subprocess.run([sys.executable, "-I", "-c", "pass"], env={"PATH": os.environ["PATH"]})

def test_starts_a_child_with_the_real_home():
    subprocess.run([sys.executable, "-I", "-c", "pass"], env=dict(os.environ, HOME=REAL))

def test_a_childs_path_reaches_this_machines_own_programs():
    subprocess.run([sys.executable, "-I", "-c", "pass"], env=dict(os.environ, PATH="/usr/bin:/bin"))

def test_runs_this_machines_own_program():
    real = shutil.which("systemctl", path="/usr/bin:/bin") or shutil.which("launchctl", path="/usr/bin:/bin")
    assert real, "neither systemctl nor launchctl here"
    subprocess.run([real, "--version" if real.endswith("systemctl") else "version"], capture_output=True)

def test_the_stub_answers_first():
    r = subprocess.run(["claude", "--version"], capture_output=True, text=True)
    assert r.returncode == 97 and "rule 17 stub" in r.stderr

def test_stays_in_its_own_home(tmp_path):
    assert os.path.realpath(os.path.expanduser("~")) != REAL
    (tmp_path / "x").write_text("x")
"""
CAUGHT = ("test_reads_the_real_pit_board_home", "test_reads_the_real_plugin_registry", "test_reads_elsewhere_in_the_home",
          "test_renames_into_the_home", "test_starts_a_child_with_no_home", "test_starts_a_child_with_the_real_home",
          "test_a_childs_path_reaches_this_machines_own_programs", "test_runs_this_machines_own_program")


def test_G20_P51_the_suites_guard_catches_each_kind_and_nothing_without_it(tmp_path):
    """P51 (the family's rule 17, THE GUARD HAS FIVE PARTS): tests/conftest.py gives the run its own home, puts loud
    stand-ins for claude, tmux, crontab, systemctl, loginctl and launchctl first on PATH, and its hook fails, in the
    test's own result, a test that reaches the real Pit Board home or plugin registry (also when it swallows the
    error), starts a child with no HOME or the real one or one whose PATH reaches this machine's own copy of one of
    those programs ahead of a stand-in, or runs this machine's own systemctl or launchctl. Control:
    the same planted tests with the guard taken out all pass."""
    import shutil
    import subprocess
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    root = tmp_path / "planted"
    (root / "tests").mkdir(parents=True)
    shutil.copy(os.path.join(here, "conftest.py"), root / "tests" / "conftest.py")
    (root / "tests" / "test_planted.py").write_text(PLANTED)

    def go():
        r = subprocess.run([sys.executable, "-m", "pytest", "-v", "-p", "no:cacheprovider", "--rootdir", str(root),
                            "-c", os.devnull, str(root / "tests")], cwd=str(root), capture_output=True, text=True,
                           timeout=120, stdin=subprocess.DEVNULL)
        return r.stdout + r.stderr

    out = go()
    verdict = {ln.split("::", 1)[1].split()[0]: ln.split()[1] for ln in out.splitlines()
               if "test_planted.py::" in ln and ln.split()[1:2] in (["PASSED"], ["FAILED"])}
    assert verdict == {**{n: "FAILED" for n in CAUGHT}, "test_the_stub_answers_first": "PASSED",
                       "test_stays_in_its_own_home": "PASSED",
                       "test_python_libraries_and_the_checkout_are_left_out": "PASSED"}, out[-4000:]
    assert "8 failed, 3 passed" in out and "rule 17: this test reached the home or the tools" in out, out[-4000:]
    for said in (".pitboard/" + "no-such-file", "plugins/no-such-file", ".local/bin/no-such-file", "-dir/x",
                 "a child with no HOME", "a child with the real HOME", "a child whose PATH reaches this machine's own", "this machine's own"):
        assert said in out, (said, out[-4000:])
    conf = root / "tests" / "conftest.py"                                # the control: no guard, nothing caught
    conf.write_text(conf.read_text().replace("sys.addaudithook(_audit)", "pass"))
    out = go()
    assert "rule 17:" not in out and "11 passed" in out, out[-4000:]


def test_G20_P51_the_guard_has_no_switch():
    """P51 (the family's rule 17, THE GUARD HAS NO SWITCH): tests/conftest.py reads no setting that could take the guard
    out of the suite's own run or send the run to the real home. Its hook and its own home are set at the top of the
    file, under no condition; the only setting it reads from the environment it was started with is PATH (to put the
    stand-ins first) and the user base (so a child finds the same pytest). The gate test above takes the hook out only
    by editing its own planted copy of the file."""
    import ast
    src = open(os.path.join(ROOT, "tests", "conftest.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    top = [ast.unparse(n) for n in tree.body if isinstance(n, ast.Expr)]
    assert "sys.addaudithook(_audit)" in top                              # never under an if, a try or a function
    assert any(t.startswith("os.environ.update(HOME=") for t in top)
    read = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            f = ast.unparse(n.func)
            if f in ("os.environ.get", "os.getenv", "os.environ.setdefault", "os.environ.pop"):
                read.append((f, ast.literal_eval(n.args[0]) if n.args and isinstance(n.args[0], ast.Constant) else
                             ast.unparse(n.args[0])))
        if isinstance(n, ast.Subscript) and ast.unparse(n.value) == "os.environ" and isinstance(n.ctx, ast.Load):
            read.append(("os.environ[]", ast.unparse(n.slice)))
        if isinstance(n, ast.Compare) and any(ast.unparse(c) == "os.environ" for c in n.comparators):
            read.append(("in os.environ", ast.unparse(n.left)))
    reads = sorted({(f, k) for f, k in read if f != "os.environ.pop"})   # pop only takes the shell's settings away
    assert reads == [("os.environ.get", "PATH"), ("os.environ.setdefault", "PYTHONUSERBASE"), ("os.environ[]", "'HOME'"),
                     ("os.environ[]", "'TMUX_TMPDIR'")], reads


def test_G20_6_P67_a_run_that_ends_early_fails_the_job(tmp_path):
    """P67 (the family's gate recipe, ninth case): a test that ends pytest's process with os._exit(0) leaves pytest's
    exit 0, no summary and no report, so a CI step that runs pytest alone is green after one test of hundreds. Every
    job's pytest step writes the JUnit report and the next step is tests/report_check.py, which fails unless the
    report holds every collected test. Planted here: the CI's own pytest command over a folder whose first test
    calls os._exit(0) exits 0 (the hole, seen), and the check after it fails; over the same folder without that test
    both pass."""
    import shutil
    import subprocess
    import sys
    text = dict(workflows())["tests.yml"]
    lines = text.splitlines()
    runs = [i for i, ln in enumerate(lines) if re.match(r"^\s+- run: python -m pytest ", ln)]
    assert len(runs) == 2, runs                                     # the Linux job and the Mac job
    for i in runs:
        assert "--junitxml=report.xml" in lines[i].split(), lines[i]
        after = [ln.strip() for ln in lines[i + 1:] if ln.strip().startswith("- ")]
        assert after and after[0] == "- run: python -I tests/report_check.py report.xml tests/", (lines[i], after[:1])
    cmd = lines[runs[0]].split("- run: ", 1)[1].split()
    assert cmd[:3] == ["python", "-m", "pytest"] and cmd[-1] == "tests/", cmd
    root = tmp_path / "planted"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_a_ends_early.py").write_text("import os\n\n\ndef test_a():\n    os._exit(0)\n")
    (root / "tests" / "test_b_runs.py").write_text("def test_b():\n    assert True\n")
    check = os.path.join(ROOT, "tests", "report_check.py")

    def run(argv):
        return subprocess.run(argv, cwd=str(root), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, timeout=120)

    def ci():
        report = root / "report.xml"
        if report.exists():
            report.unlink()
        step = run([sys.executable] + cmd[1:3] + ["-p", "no:cacheprovider", "--rootdir", str(root), "-c", os.devnull]
                   + cmd[3:])
        return step, run([sys.executable, "-I", check, "report.xml", "tests/"])

    step, after = ci()
    assert step.returncode == 0, (step.returncode, step.stdout[-800:])          # the hole: pytest alone says green
    assert after.returncode == 1 and "no readable test report" in after.stdout, (after.returncode, after.stdout)
    (root / "tests" / "test_a_ends_early.py").unlink()
    shutil.rmtree(root / "tests" / "__pycache__", ignore_errors=True)
    step, after = ci()
    assert step.returncode == 0 and after.returncode == 0, (step.stdout[-800:], after.stdout)
    assert "1 of 1 collected tests are in the report" in after.stdout, after.stdout
