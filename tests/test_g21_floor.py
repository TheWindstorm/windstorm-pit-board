"""G21.15 (plan 1.26, P16): the Python floor is 3.9, and it is checked as the launcher's first act.

A sister skill named "Python 3.10+" without checking it; on a stock Python 3.8 it registered and started a service
before it crashed. Here 3.8 ran, but with no zoneinfo it showed wrong times with no error. So below the floor
Pit Board makes nothing and says, in one true line, what it needs and what it found."""
import ast
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

from pitboard import cli, launch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCH = os.path.join(ROOT, "pitboard", "launch.py")
WANT = "3.9"


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def test_G21_15_the_floor_is_one_version_in_every_place():
    """FLOOR, Part 0 rule 4, G21.15, the README and the lowest Python in CI name the same version."""
    assert "{}.{}".format(*launch.FLOOR) == WANT
    plan = _read("DNA-STRAND-MASTER-PLAN.md")
    assert re.search(r"^4\. \*\*Python ([0-9.]+) or newer, standard library only\.\*\*", plan, re.M).group(1) == WANT
    assert re.search(r"^\*\*G21\.15 The Python floor\*\*.*?Pit Board runs on Python ([0-9.]+) or newer", plan,
                     re.M).group(1) == WANT
    assert re.findall(r"Python ([0-9.]+) or newer", _read("README.md")) == [WANT]
    pythons = re.search(r'^\s*python: \[([^\]]*)\]', _read(".github", "workflows", "tests.yml"), re.M).group(1)
    found = [p.strip().strip('"') for p in pythons.split(",")]
    assert min(found, key=lambda v: tuple(int(x) for x in v.split("."))) == WANT


@pytest.fixture
def old(tmp_path, monkeypatch):
    """A Python 3.8.20, below the floor, with an empty HOME and Pit Board home: nothing may appear in them."""
    monkeypatch.setattr(launch, "_found", lambda: (3, 8, 20))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PITBOARD_HOME", str(tmp_path / "pb"))
    return tmp_path


class Pipe:
    def __init__(self):
        self.text = ""

    def write(self, s):
        self.text += s


def _run(main, argv, capsys):
    code = main(argv)
    got = capsys.readouterr()
    return code, got.out, got.err


@pytest.mark.parametrize("main", [launch.main, cli.main], ids=["launch", "cli"])
def test_G21_15_below_the_floor_nothing_is_made_and_one_true_line_is_said(old, main, capsys):
    """The launcher's first act, and cli.main()'s for a launcher copy from before 0.1.3."""
    hook = _run(main, ["hook", "session-start"], capsys)
    assert hook[0] == 0 and hook[1] == ""
    assert hook[2] == "Pit Board needs Python 3.9 or newer; found 3.8.20 at {}\n".format(sys.executable)
    assert _run(main, ["status"], capsys) == (0, "Pit Board needs Python 3.9 or newer, found 3.8.20", "")
    for argv in (["setup", "--minimal", "--apply"], ["add", "a question", "--kind", "question"], ["version"]):
        code, out, err = _run(main, argv, capsys)
        assert (code, out) == (10, ""), argv
        assert err.splitlines() == ["Pit Board needs Python 3.9 or newer; found 3.8.20 at {}".format(sys.executable),
                                    "pitboard: install Python 3.9 or newer, or put one first on PATH as python3"]
    assert os.listdir(old) == []                                              # no home, no log, no lock, no copy


def test_G21_15_at_the_floor_it_runs(old, monkeypatch, capsys):
    monkeypatch.setattr(launch, "_found", lambda: (3, 9, 6))                  # the Mac's own /usr/bin/python3
    assert launch.floor_refusal(["status"]) is None
    assert cli.main(["version"], stdout=Pipe(), stderr=Pipe()) == 0


NEWER = tuple(getattr(ast, n) for n in ("NamedExpr", "Match", "TryStar") if hasattr(ast, n))


def newer_grammar(src):
    """What 3.6 cannot read: :=, match, except*, positional-only parameters, f"{x=}". (ast.parse's
    feature_version does not refuse all of these on every Python, so the tree is read instead.)"""
    found = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, NEWER):
            found.append(type(node).__name__)
        if isinstance(node, ast.arguments) and getattr(node, "posonlyargs", []):
            found.append("positional-only")
    found += ["f-string =" for _ in re.finditer(r"\{[^{}]*=\}", src)]
    return found


def test_G21_15_the_launcher_is_readable_by_older_grammar():
    """So an older interpreter reaches the check instead of stopping on a syntax error."""
    assert newer_grammar(_read("pitboard", "launch.py")) == []
    assert newer_grammar("if (n := 1):\n    pass\n") == ["NamedExpr"]           # the check does bite
    assert newer_grammar("def f(a, /):\n    pass\n") == ["positional-only"]
    assert newer_grammar('x = f"{y=}"\n') == ["f-string ="]


OLDER = next((shutil.which(n) for n in ("python3.8", "python3.7", "python3.6") if shutil.which(n)), None)


@pytest.mark.skipif(OLDER is None, reason="no Python older than the floor on this machine (python3.6 to python3.8)")
def test_G21_15_a_real_older_python_is_refused_before_anything(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path / "home"), PITBOARD_HOME=str(tmp_path / "pb"))
    for argv, code in ((["hook", "session-start"], 0), (["status"], 0), (["setup", "--minimal", "--apply"], 10)):
        p = subprocess.run([OLDER, "-I", LAUNCH] + argv, input=json.dumps({}), capture_output=True, text=True,
                           env=env, timeout=60)
        assert p.returncode == code, (argv, p.stderr)
        assert "Pit Board needs Python 3.9 or newer" in (p.stdout + p.stderr), argv
        assert "Traceback" not in p.stderr, argv
    assert os.listdir(tmp_path) == []
