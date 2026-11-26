"""P138 (G21.1): no release tag is pushed before the whole suite has passed with that tag at its head.

    python3 -I tests/release_step.py <the release commit, all 40 characters> [--push] [--origin URL]

The check that refuses a release tag acts only where that tag points at the checked-out commit. A branch's run
never has one, and a tag's push starts no run, so a tag could be pushed green and fail its own suite (seen at
v0.1.3). This step makes a fresh clone of the origin, checks out the commit, makes the tag vX.Y.Z there (X.Y.Z as
that commit's .claude-plugin/plugin.json says), and runs the suite in that clone as CI runs it: pytest with its
JUnit report, then tests/report_check.py. The tag is pushed from that clone only with --push and only where both
ended exit 0; then it is read back from the origin. Without --push the run is a rehearsal and pushes nothing.
Anything else pushes nothing and ends exit 1 with a line that says why. A tag of that name already at the origin
is refused before the suite runs: a release tag is never moved or remade. The clone is removed in every case, and
the tree this file is run from is not touched. --origin names another origin than this checkout's (the tests use it).
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USAGE = "usage: release_step.py <the release commit, all 40 characters> [--push] [--origin URL]"
MAX_SECONDS = 3600


class Refused(Exception):
    pass


def git(where, *cmd):
    r = subprocess.run(["git", "-C", where] + list(cmd), stdin=subprocess.DEVNULL, capture_output=True, text=True,
                       errors="replace", timeout=600, check=False)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def must(where, what, *cmd):
    rc, out, err = git(where, *cmd)
    if rc != 0:
        raise Refused(f"{what} (git ended exit {rc}: {(err or out).splitlines()[-1] if (err or out) else 'no words'})")
    return out


def run(cmd, cwd):
    """The command with its lines passed on as they come: (exit code, its last line with words). Its whole process
    group is ended after MAX_SECONDS, and when this step is interrupted."""
    p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, errors="replace", start_new_session=True,
                         env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))

    def end():
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
    late = threading.Timer(MAX_SECONDS, end)
    late.start()
    last = ""
    try:
        for line in p.stdout:
            print("  | " + line.rstrip("\n"), flush=True)
            last = line.strip() or last
        return p.wait(), last
    finally:
        late.cancel()
        if p.poll() is None:
            end()
            p.wait()


def step(commit, origin, push, work):
    clone, report = os.path.join(work, "clone"), os.path.join(work, "report.xml")
    must(work, "the origin could not be cloned", "clone", "-q", origin, clone)
    must(clone, "the origin does not hold that commit", "checkout", "-q", "--detach", commit)
    if must(clone, "the clone's commit could not be read", "rev-parse", "HEAD") != commit:
        raise Refused("the clone is not at that commit")
    try:
        with open(os.path.join(clone, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            version = json.load(f).get("version")
    except (OSError, ValueError, AttributeError):
        version = None
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise Refused(f"that commit's .claude-plugin/plugin.json names no version X.Y.Z ({version!r})")
    tag = "v" + version
    if must(clone, "the origin's tags could not be read", "ls-remote", "origin", "refs/tags/" + tag):
        raise Refused(f"{tag} is already at the origin, and a release tag is never moved or remade")
    must(clone, "the tag could not be made in the clone", "tag", "-a", tag, "-m", f"Windstorm Pit Board {version}")
    print(f"release step: commit {commit}, tag {tag} made in a fresh clone, pushed nowhere; the suite runs there now",
          flush=True)
    rc, last = run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--junitxml=" + report, "tests/"],
                   clone)
    print(f"release step: pytest ended exit {rc}; its last line: {last}", flush=True)
    rc2, _ = run([sys.executable, "-I", os.path.join("tests", "report_check.py"), report, "tests/"], clone)
    print(f"release step: report_check ended exit {rc2}", flush=True)
    if rc != 0 or rc2 != 0:
        raise Refused(f"the suite did not pass with {tag} at its head")
    if must(clone, "the tag could not be read", "rev-parse", tag + "^{commit}") != commit:
        raise Refused(f"after the suite, {tag} in the clone is not at that commit")
    if not push:
        return f"the suite passed with {tag} at its head. This run was a rehearsal (no --push). Nothing was pushed."
    must(clone, f"the push of {tag} failed", "push", "-q", "origin", f"refs/tags/{tag}:refs/tags/{tag}")
    back = dict(reversed(ln.split("\t")) for ln in must(
        clone, "the pushed tag could not be read back", "ls-remote", "origin", f"refs/tags/{tag}",
        f"refs/tags/{tag}^{{}}").splitlines() if "\t" in ln)
    obj, at = back.get(f"refs/tags/{tag}"), back.get(f"refs/tags/{tag}^{{}}")
    if obj != must(clone, "the tag could not be read", "rev-parse", tag) or at != commit:
        raise Refused(f"{tag} WAS PUSHED, and the origin reads back tag object {obj} at commit {at}, not what this "
                      "run made")
    return f"the suite passed with {tag} at its head; {tag} pushed; the origin reads back tag object {obj} at commit {at}."


def main(argv):
    push, origin, rest = False, None, []
    args = list(argv)
    while args:
        a = args.pop(0)
        if a == "--push":
            push = True
        elif a == "--origin" and args:
            origin = args.pop(0)
        else:
            rest.append(a)
    if len(rest) != 1 or not re.fullmatch(r"[0-9a-f]{40}", rest[0]):
        print(USAGE)
        return 2
    if origin is None:
        rc, origin, _ = git(ROOT, "remote", "get-url", "origin")
        if rc != 0 or not origin:
            print("release step: REFUSED. This checkout names no origin. Nothing was pushed.")
            return 1
    work = tempfile.mkdtemp(prefix="pitboard-release-step-")
    try:
        print("release step: " + step(rest[0], origin, push, work))
        return 0
    except Refused as e:
        pushed = "WAS PUSHED" in str(e)
        print(f"release step: REFUSED. {e}." + ("" if pushed else " Nothing was pushed."))
        return 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
