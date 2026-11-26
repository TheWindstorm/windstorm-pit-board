"""P138 (#217, G21.1): no release tag is pushed before the whole suite has passed with that tag at its head.

Seen 2026-11-26 at the tag v0.1.3: the tag was pushed after CI on main was read green, and in a fresh clone of the
pushed tag one test of the suite failed, the tag check. No run could have shown it: the check acts only where a
release tag points at the checked-out commit, a branch never has one, and a tag's push starts no run.

The release step (tests/release_step.py) therefore makes the tag locally in a fresh clone of the release commit, runs
the suite there as CI runs it (pytest with its report, then tests/report_check.py), and pushes the tag only where both
ended exit 0 and --push was given. These tests hold the refusal with a made origin: a small repository whose one test
is green on a branch and red with a release tag at its head, which is the fault as it was seen."""
import json
import os
import shutil
import site
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEP = os.path.join(ROOT, "tests", "release_step.py")
pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="no git here")

RED_WITH_A_TAG = '''import subprocess
def test_made():
    tags = subprocess.run(["git", "tag", "--points-at", "HEAD"], capture_output=True, text=True).stdout.split()
    assert not tags, tags
'''
GREEN = "def test_made():\n    assert True\n"
ENDS_EARLY = "import os\ndef test_made():\n    os._exit(0)\n"
NEVER = "v9.9.9 is already at the origin, and a release tag is never moved or remade"


class Made:
    """A made origin (a bare repository) with one commit: a version label, a tests folder with the real report check
    and one test."""

    def __init__(self, tmp_path, test, version="9.9.9"):
        self.tmp = tmp_path
        self.env = dict(os.environ, HOME=str(tmp_path / "home"), TMPDIR=str(tmp_path / "t"),
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, PYTHONUSERBASE=site.getuserbase(),
                        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
        for d in ("home", "t", "src/.claude-plugin", "src/tests"):
            (tmp_path / d).mkdir(parents=True)
        src = tmp_path / "src"
        (src / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "made", "version": version}))
        shutil.copy(os.path.join(ROOT, "tests", "report_check.py"), src / "tests" / "report_check.py")
        (src / "tests" / "test_made.py").write_text(test)
        for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "release"]):
            self.git(src, *cmd)
        self.src, self.commit = src, self.git(src, "rev-parse", "HEAD")
        self.origin = tmp_path / "origin.git"
        self.git(tmp_path, "clone", "-q", "--bare", str(src), str(self.origin))

    def git(self, where, *cmd):
        return subprocess.run(["git", "-C", str(where)] + list(cmd), check=True, env=self.env, capture_output=True,
                              text=True, timeout=60).stdout.strip()

    def step(self, *args, commit=None):
        r = subprocess.run([sys.executable, "-I", STEP, commit or self.commit, "--origin", "file://" + str(self.origin)]
                           + list(args), env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=300, cwd=str(self.tmp), check=False)
        return r.returncode, r.stdout + r.stderr

    def tags_at_origin(self):
        return self.git(self.origin, "tag", "-l").split()

    def faults(self, rc, said, want_rc, pushed):
        """What every case holds: the exit code, the origin's tags, the last line's word, and nothing left behind."""
        last = (said.rstrip().splitlines() or [""])[-1]
        return [what for what, wrong in [
            (f"exit {rc}, not {want_rc}", rc != want_rc),
            (f"the origin's tags are {self.tags_at_origin()}", self.tags_at_origin() != (["v9.9.9"] if pushed else [])),
            (f"the last line does not say that nothing was pushed: {last!r}", not pushed and "Nothing was pushed" not in last),
            ("the tree the step was pointed from got a tag", bool(self.git(self.src, "tag", "-l"))),
            (f"something is left in the temporary folder: {os.listdir(self.tmp / 't')}", bool(os.listdir(self.tmp / "t"))),
        ] if wrong]


def test_G21_1_P138_a_suite_that_is_red_with_the_tag_at_its_head_pushes_no_tag(tmp_path):
    m = Made(tmp_path, RED_WITH_A_TAG)
    subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/"], cwd=str(m.src),
                   env=m.env, check=True, capture_output=True, timeout=120)       # the control: green on the branch
    rc, said = m.step("--push")
    faults = m.faults(rc, said, 1, pushed=False)
    assert not faults and "REFUSED" in said and "1 failed" in said, (faults, said)


def test_G21_1_P138_a_run_that_ends_early_pushes_no_tag_though_pytest_ended_exit_0(tmp_path):
    m = Made(tmp_path, ENDS_EARLY)
    rc, said = m.step("--push")
    faults = m.faults(rc, said, 1, pushed=False)
    assert not faults and "REFUSED" in said and "pytest ended exit 0" in said and "report_check ended exit 1" in said, \
        (faults, said)


def test_G21_1_P138_a_green_suite_without_the_push_word_is_a_rehearsal(tmp_path):
    m = Made(tmp_path, GREEN)
    rc, said = m.step()
    faults = m.faults(rc, said, 0, pushed=False)
    assert not faults and "1 passed" in said and "REFUSED" not in said, (faults, said)


def test_G21_1_P138_a_green_suite_with_the_push_word_pushes_the_tag_and_reads_it_back(tmp_path):
    m = Made(tmp_path, GREEN)
    rc, said = m.step("--push")
    faults = m.faults(rc, said, 0, pushed=True)
    assert not faults and "1 passed" in said, (faults, said)
    assert m.git(m.origin, "rev-parse", "v9.9.9^{commit}") == m.commit
    assert m.git(m.origin, "cat-file", "-t", "v9.9.9") == "tag"                  # annotated, as every release tag is
    assert m.git(m.origin, "rev-parse", "v9.9.9") in said and m.commit in said   # the read-back is printed
    was = m.git(m.origin, "rev-parse", "v9.9.9")
    rc, said = m.step("--push")                                                  # a tag is never moved or remade
    assert rc == 1 and "REFUSED" in said and NEVER in said and "passed" not in said, said
    assert m.git(m.origin, "rev-parse", "v9.9.9") == was and not os.listdir(tmp_path / "t")


def test_G21_1_P138_a_tag_of_that_name_on_another_commit_at_the_origin_is_refused_before_the_suite_runs(tmp_path):
    """Refused by the step's own read of the origin and in its own words, not by whatever git says later."""
    m = Made(tmp_path, GREEN)
    apart = m.git(m.origin, "commit-tree", m.git(m.origin, "rev-parse", "HEAD^{tree}"), "-m", "apart")
    m.git(m.origin, "tag", "v9.9.9", apart)
    rc, said = m.step("--push")
    assert rc == 1 and "REFUSED" in said and NEVER in said and "passed" not in said, said
    assert m.git(m.origin, "rev-parse", "v9.9.9") == apart and not os.listdir(tmp_path / "t")


@pytest.mark.parametrize("word", ["abc1234", "HEAD", "main", ""])
def test_G21_1_P138_the_commit_is_named_by_all_its_40_characters(tmp_path, word):
    m = Made(tmp_path, GREEN)
    rc, said = m.step("--push", commit=word or m.commit[:39])
    assert rc == 2 and "all 40 characters" in said, said                         # the step's own usage line
    assert m.tags_at_origin() == [] and "passed" not in said and not os.listdir(tmp_path / "t"), said


def test_G21_1_P138_a_commit_the_origin_does_not_hold_pushes_no_tag(tmp_path):
    m = Made(tmp_path, GREEN)
    rc, said = m.step("--push", commit="0" * 40)
    faults = m.faults(rc, said, 1, pushed=False)
    assert not faults and "REFUSED" in said and "passed" not in said, (faults, said)


def test_G21_1_P138_a_version_label_that_is_no_version_pushes_no_tag(tmp_path):
    m = Made(tmp_path, GREEN, version="9.9")
    rc, said = m.step("--push")
    assert rc == 1 and "REFUSED" in said and m.tags_at_origin() == [] and "passed" not in said, said
    assert not os.listdir(tmp_path / "t")
