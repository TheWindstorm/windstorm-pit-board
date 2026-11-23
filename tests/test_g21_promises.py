"""G21.14: PROMISES.json, a lesson from real use is a gate.

These tests refuse the version in .claude-plugin/plugin.json while a promise due in it is not built,
and the version after it until the promise was seen to work on a real machine. Each test checks the
real file, and also that a planted bad copy is refused, so the gate itself cannot go soft.
"""
import ast
import collections
import copy
import functools
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import warnings
import xml.etree.ElementTree as ET

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHOLE = ("id", "seen", "promise", "codon", "owner", "first_ship_in", "ship_in")
RUN_SECONDS = 120
NO_REASON = ("", "unconditional skip")                       # what pytest writes for a skip given no reason
INNER = "PITBOARD_PROMISES_GATE_INNER"


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _v(s):
    return tuple(int(x) for x in s.split("."))


def twice_defined(tests_dir):
    """Plan 1.20: test names defined twice in one file (module level or in one class). Only the last
    definition runs, and the runner still reports a pass under that name."""
    out = []
    for name in sorted(os.listdir(tests_dir)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        with open(os.path.join(tests_dir, name), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        bodies = [("", tree.body)] + [(n.name + ".", n.body) for n in tree.body if isinstance(n, ast.ClassDef)]
        for prefix, body in bodies:
            count = collections.Counter(d.name for d in body
                                        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and d.name.startswith("test_"))
            out += [f"{name}: {prefix}{t} is defined {c} times, and only the last one runs"
                    for t, c in sorted(count.items()) if c > 1]
    return out


def _skips_always(node):
    """True for a skip that does not depend on the machine: a `skip` mark (called or not), or a `skipif`
    whose condition is the constant True."""
    f = node.func if isinstance(node, ast.Call) else node
    if not isinstance(f, ast.Attribute):
        return False
    if f.attr == "skip":
        return isinstance(f.value, ast.Attribute) and f.value.attr == "mark"
    if f.attr == "skipif" and isinstance(node, ast.Call) and node.args:
        return isinstance(node.args[0], ast.Constant) and node.args[0].value is True
    return False


def _skips_in_body(body):
    """A `pytest.skip(...)` that is not under a condition (top level of the test, or in a `with`)."""
    for st in body:
        if isinstance(st, ast.With) and _skips_in_body(st.body):
            return True
        if (isinstance(st, ast.Expr) and isinstance(st.value, ast.Call) and isinstance(st.value.func, ast.Attribute)
                and st.value.func.attr == "skip" and isinstance(st.value.func.value, ast.Name)
                and st.value.func.value.id == "pytest"):
            return True
    return False


def always_skipped(tests_dir):
    """Plan 1.20: test names skipped unconditionally, so they run on no machine, whatever the reason."""
    out = set()
    for name in sorted(os.listdir(tests_dir)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        with open(os.path.join(tests_dir, name), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        whole_file = any(isinstance(st, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in st.targets)
                         and any(_skips_always(n) for n in ast.walk(st.value)) for st in tree.body)
        groups = [(whole_file, tree.body)] + [(whole_file or any(_skips_always(d) for d in c.decorator_list), c.body)
                                              for c in tree.body if isinstance(c, ast.ClassDef)]
        for always, body in groups:
            for d in body:
                if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and d.name.startswith("test_"):
                    if always or any(_skips_always(x) for x in d.decorator_list) or _skips_in_body(d.body):
                        out.add(d.name)
    return out


def _stop(p):
    """Stop the child: its whole process group when it leads its own, else only the child by its exact
    process id. Never the suite's group (or a person's shell), even if the new session did not take."""
    try:
        group = os.getpgid(p.pid)
    except ProcessLookupError:
        group = None
    if group is not None and group == p.pid and group != os.getpgrp():
        os.killpg(group, signal.SIGKILL)
    else:
        p.kill()
    p.communicate()


def runner_outcomes(root, names, seconds=RUN_SECONDS):
    """Plan 1.20: what the test runner itself reports for each name, from its own JUnit report:
    {name: ("passed",) | ("skipped", reason) | ("failed",)}. A name the runner does not collect is absent.
    Runs only those tests (never the gate), in its own process group with a time limit, and leaves
    nothing behind: its report and its temporary folders are in one folder removed whatever happens."""
    if not names:
        return {}
    if os.environ.get(INNER) and os.path.realpath(root) == os.path.realpath(ROOT):
        raise RuntimeError("the promise gate does not run itself again")
    out, cases = {}, collections.defaultdict(list)
    with tempfile.TemporaryDirectory(prefix="pitboard-gate-") as tmp:
        report = os.path.join(tmp, "report.xml")
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "junit_family=xunit2",
               f"--junitxml={report}", f"--basetemp={os.path.join(tmp, 'base')}", "-k", " or ".join(sorted(names)),
               os.path.join(root, "tests")]
        p = subprocess.Popen(cmd, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             env=dict(os.environ, **{INNER: "1"}), start_new_session=True)
        try:
            text = p.communicate(timeout=seconds)[0].decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            raise AssertionError(f"the promise tests did not finish in {seconds} s") from None
        finally:
            if p.returncode is None:
                _stop(p)
        if not os.path.exists(report):
            raise AssertionError("the test runner wrote no report:\n" + text[-2000:])
        for case in ET.parse(report).getroot().iter("testcase"):
            base = case.get("name", "").split("[")[0]
            if base not in names:
                continue
            skipped = case.find("skipped")
            if case.find("failure") is not None or case.find("error") is not None:
                cases[base].append(("failed",))
            elif skipped is not None:
                cases[base].append(("skipped", (skipped.get("message") or "").strip()))
            else:
                cases[base].append(("passed",))
    for name, got in cases.items():
        out[name] = (next((c for c in got if c[0] == "failed"), None) or next((c for c in got if c[0] == "skipped"), None)
                     or ("passed",))
    return out


@functools.lru_cache(maxsize=1)
def _real_runner():
    doc = json.loads(_read("PROMISES.json"))
    return runner_outcomes(ROOT, {r["test"] for r in doc["rows"] if r.get("test")})


def _world():
    """The real promises, version and plan text, and what the test runner reports for the rows' tests."""
    return {
        "doc": json.loads(_read("PROMISES.json")),
        "version": _v(json.loads(_read(".claude-plugin", "plugin.json"))["version"]),
        "plan": _read("DNA-STRAND-MASTER-PLAN.md"),
        "runner": dict(_real_runner()),
        "twice": twice_defined(os.path.join(ROOT, "tests")),
        "always_skipped": always_skipped(os.path.join(ROOT, "tests")),
    }


def whole_problems(w):
    out, ids = [], [r.get("id") for r in w["doc"]["rows"]]
    if len(ids) != len(set(ids)):
        out.append("two rows share an id")
    for r in w["doc"]["rows"]:
        out += [f"{r.get('id')}: '{k}' is empty" for k in WHOLE if not r.get(k)]
        if r.get("owner") not in ("person", "maintainer"):
            out.append(f"{r.get('id')}: owner must be 'person' or 'maintainer'")
        if "kind" in r and r["kind"] != "guard":                                # plan 1.23
            out.append(f"{r.get('id')}: kind, when given, must be 'guard'")
        for k in ("first_ship_in", "ship_in"):
            if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(r.get(k, ""))):
                out.append(f"{r.get('id')}: {k} is not MAJOR.MINOR.PATCH")
        if r.get("codon") and not re.search(r"\*\*" + re.escape(r["codon"]) + r"(?![0-9])", w["plan"]):
            out.append(f"{r['id']}: codon {r['codon']} is not in the plan")
    return out


def declined_problems(w):
    return ["a declined lesson needs what was heard and why it was not taken"
            for d in w["doc"].get("declined", []) if not (d.get("heard") and d.get("why"))]


def unbuilt_problems(w):
    """Plan 1.20: a row's test counts only when the runner collects it and runs it to a pass. Every row that
    names a test is checked at every version; a row due by this version must name one."""
    out = []
    for r in w["doc"]["rows"]:
        t = r.get("test") or ""
        if not t:
            if _v(r["ship_in"]) <= w["version"]:
                out.append(f"{r['id']} ({r['promise'][:60]}...) is due in {r['ship_in']} and has no test. "
                           "Build it, or have its date moved (see how_to_use in PROMISES.json).")
            continue
        if not t.startswith("test_" + r["codon"].replace(".", "_") + "_"):
            out.append(f"{r['id']}: its test {t} is not named with its codon {r['codon']}")
        got = w["runner"].get(t)
        if got is None:
            out.append(f"{r['id']}: its test {t} is not one the test runner collects (renamed, in a string, "
                       "under a helper, or missing)")
        elif got[0] == "failed":
            out.append(f"{r['id']}: its test {t} fails")
        elif got[0] == "skipped" and got[1] in NO_REASON:
            out.append(f"{r['id']}: its test {t} is skipped with no reason")
        elif got[0] == "skipped" and t in w["always_skipped"]:
            out.append(f"{r['id']}: its test {t} is skipped unconditionally ({got[1]}), so it runs on no machine")
        out += [f"{r['id']}: {x}" for x in w["twice"] if f" {t} is defined " in x or f".{t} is defined " in x]
    return out


def not_run_here(w):
    """Rows whose test was skipped here for a written reason: listed, and not a pass."""
    return [f"{r['id']}: its test {r['test']} was not run here ({w['runner'][r['test']][1]})"
            for r in w["doc"]["rows"]
            if r.get("test") and w["runner"].get(r["test"], ("",))[0] == "skipped"
            and w["runner"][r["test"]][1] not in NO_REASON and r["test"] not in w["always_skipped"]]


def unproven_problems(w):
    return [f"{r['id']} was due in {r['ship_in']} and no real machine has proven it yet"
            for r in w["doc"]["rows"] if _v(r["ship_in"]) < w["version"] and not r.get("proven")]


def moved_problems(w):
    out = []
    for r in w["doc"]["rows"]:
        if r["ship_in"] != r["first_ship_in"]:
            if not r.get("moved_why"):
                out.append(f"{r['id']}: its date moved with no reason written")
            if r["owner"] == "person" and not r.get("moved_by_person"):
                out.append(f"{r['id']}: only the person who saw it can move its date")
    return out


def _planted(w, **row):
    """A copy of the real world with one more row (whole unless the caller says otherwise)."""
    p = copy.deepcopy(w)
    base = {"id": "PX", "seen": "planted", "promise": "planted promise", "codon": "G10.5", "owner": "person",
            "first_ship_in": "0.1.0", "ship_in": "0.1.0", "test": "test_G10_5_wrapper_joins_the_operator_line_and_the_segment",
            "proven": "planted", "moved_why": "", "moved_by_person": ""}
    base.update(row)
    p["doc"]["rows"].append(base)
    return p


def test_G21_14_every_row_is_whole_and_its_codon_is_in_the_plan():
    w = _world()
    assert whole_problems(w) == []
    assert whole_problems(_planted(w, seen="")) == ["PX: 'seen' is empty"]
    assert whole_problems(_planted(w, codon="G99.1")) == ["PX: codon G99.1 is not in the plan"]
    assert whole_problems(_planted(w, id=w["doc"]["rows"][0]["id"])) == ["two rows share an id"]
    assert whole_problems(_planted(w, kind="guard")) == []
    assert whole_problems(_planted(w, kind="lesson")) == ["PX: kind, when given, must be 'guard'"]


def test_G21_14_a_lesson_not_taken_is_written_down_with_its_reason():
    w = _world()
    assert declined_problems(w) == []
    p = copy.deepcopy(w)
    p["doc"].setdefault("declined", []).append({"heard": "something", "why": ""})
    assert len(declined_problems(p)) == 1


def test_G21_14_no_version_ships_while_a_promise_due_in_it_is_not_built():
    w = _world()
    assert unbuilt_problems(w) == []
    for line in not_run_here(w):
        warnings.warn(line)                                                      # listed, and not a pass
    assert len(unbuilt_problems(_planted(w, test=""))) == 1                       # due now, no test
    assert len(unbuilt_problems(_planted(w, test="test_G10_5_does_not_exist"))) == 1
    assert len(unbuilt_problems(_planted(w, test="test_INV2_cache_can_be_deleted_without_loss"))) == 1  # wrong codon
    assert unbuilt_problems(_planted(w, test="", first_ship_in="99.0.0", ship_in="99.0.0")) == []   # not due yet
    assert len(unbuilt_problems(_planted(w, test="test_G10_5_does_not_exist", first_ship_in="99.0.0",
                                         ship_in="99.0.0"))) == 1                # a named test: checked at any version


SCRATCH = '''import os
import time

import pytest


def test_G1_1_real():
    assert True


@pytest.mark.skipif(not os.environ.get("PB_GATE_NEVER_SET"), reason="another system")
def test_G1_1_skipped_for_a_reason():
    assert True


@pytest.mark.skip
def test_G1_1_skipped_bare():
    assert True


@pytest.mark.skip(reason="later")
def test_G1_1_skipped_always_with_a_reason():
    assert True


def test_G1_1_skipped_in_its_body():
    pytest.skip("not today")


_TEXT = """
def test_G1_1_in_a_string():
    assert True
"""


def _helper():
    return None

    def test_G1_1_after_a_return():
        assert True


if False:
    def test_G1_1_under_if_false():
        assert True


def test_G1_1_shadowed():
    assert False


def test_G1_1_shadowed():
    pass


def test_G1_1_fails():
    assert False


def test_G1_1_hangs():
    with open(os.environ["PB_GATE_PIDS"], "a") as f:
        f.write(f"{os.getpid()}\\n")
    time.sleep(60)
'''
SCRATCH_NAMES = ("real", "skipped_for_a_reason", "skipped_bare", "skipped_always_with_a_reason", "skipped_in_its_body",
                 "in_a_string", "after_a_return", "under_if_false", "shadowed", "fails")


def _scratch(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_scratch.py").write_text(SCRATCH)
    return tmp_path


def test_G21_14_the_gate_counts_only_tests_the_runner_runs(tmp_path):
    """P11: a planted test that cannot run, six ways, is refused; only the real one counts."""
    root = _scratch(tmp_path)
    names = {f"test_G1_1_{n}" for n in SCRATCH_NAMES}
    got = runner_outcomes(str(root), names)
    assert got == {"test_G1_1_real": ("passed",), "test_G1_1_skipped_for_a_reason": ("skipped", "another system"),
                   "test_G1_1_skipped_bare": ("skipped", "unconditional skip"),
                   "test_G1_1_skipped_always_with_a_reason": ("skipped", "later"),
                   "test_G1_1_skipped_in_its_body": ("skipped", "not today"), "test_G1_1_shadowed": ("passed",),
                   "test_G1_1_fails": ("failed",)}          # in a string, after a return, under if False: not collected
    w = {"doc": {"rows": [{"id": n, "codon": "G1.1", "ship_in": "0.1.0", "promise": n, "test": f"test_G1_1_{n}"}
                          for n in SCRATCH_NAMES]},
         "version": (0, 1, 0), "runner": got, "twice": twice_defined(str(root / "tests")),
         "always_skipped": always_skipped(str(root / "tests"))}
    problems = unbuilt_problems(w)
    assert [p.split(":")[0] for p in problems] == ["skipped_bare", "skipped_always_with_a_reason", "skipped_in_its_body",
                                                   "in_a_string", "after_a_return", "under_if_false", "shadowed", "fails"]
    assert "skipped unconditionally (later), so it runs on no machine" in problems[1]
    assert "defined 2 times, and only the last one runs" in problems[6]
    assert not_run_here(w) == ["skipped_for_a_reason: its test test_G1_1_skipped_for_a_reason was not run here (another system)"]


def test_G21_14_the_gate_has_a_time_limit_and_leaves_nothing_behind(tmp_path, monkeypatch):
    root = _scratch(tmp_path)
    pids = tmp_path / "pids"
    monkeypatch.setenv("PB_GATE_PIDS", str(pids))
    before = set(os.listdir(tempfile.gettempdir()))
    with pytest.raises(AssertionError, match="did not finish in 5 s"):
        runner_outcomes(str(root), {"test_G1_1_hangs"}, seconds=5)
    pid = int(pids.read_text().split()[0])                                       # the test that hung, a grandchild
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert [n for n in set(os.listdir(tempfile.gettempdir())) - before if n.startswith("pitboard-gate-")] == []


def test_G21_14_the_time_limit_never_stops_the_suites_own_group(monkeypatch):
    """If the child did not get its own process group, only the child is stopped, by its exact process id."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdout=subprocess.PIPE)  # suite's group
    groups = []
    monkeypatch.setattr(os, "killpg", lambda g, sig: groups.append(g))
    _stop(child)
    assert groups == [] and child.returncode is not None and child.returncode < 0
    own = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdout=subprocess.PIPE,
                           start_new_session=True)
    monkeypatch.undo()
    _stop(own)
    assert own.returncode is not None and own.returncode < 0


def test_G21_14_the_version_after_needs_proof_on_a_real_machine():
    w = _world()
    assert unproven_problems(w) == []
    now = ".".join(str(n) for n in w["version"])        # the planted row is due in the version being built
    after = dict(w, version=(w["version"][0], w["version"][1], w["version"][2] + 1))
    planted = [x for x in unproven_problems(_planted(after, proven="", first_ship_in=now, ship_in=now))
               if x.startswith("PX ")]
    assert len(planted) == 1                                                     # the next version is refused
    assert unproven_problems(_planted(w, proven="", first_ship_in=now, ship_in=now)) == []   # its own version is not


def test_G21_14_a_date_moves_only_with_a_reason_and_a_persons_row_only_by_their_word():
    w = _world()
    assert moved_problems(w) == []
    assert moved_problems(_planted(w, ship_in="0.2.0")) == [
        "PX: its date moved with no reason written", "PX: only the person who saw it can move its date"]
    assert moved_problems(_planted(w, ship_in="0.2.0", moved_why="late")) == [
        "PX: only the person who saw it can move its date"]
    assert moved_problems(_planted(w, owner="maintainer", ship_in="0.2.0", moved_why="late")) == []
