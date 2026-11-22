"""Refreshing the stable launcher copy from a session start (plan G21.4, G7.1 step 5).

Until `pitboard self-update` exists, the session-start hook of an installed version refreshes the
home's copy of `bin/pitboard` and `pitboard/launch.py` when it came from an older version (or is
torn), so a launcher fix reaches homes set up by an earlier release. A broken launcher never
replaces a working one: the new files are written whole into a temporary folder in the stable
copy's layout, that folder's `bin/pitboard version` must answer, and only then are those same files
renamed over the copy, the old copy kept as one `.prev` backup, `copied-from` written last.
Any number of hooks doing this at once leave one whole copy (same content, the last rename wins).
Standard library only.
"""
import os
import re
import shutil
import subprocess
import tempfile
import time

from . import __version__, launch

FILES = ((os.path.join("bin", "pitboard"), 0o755), (os.path.join("pitboard", "launch.py"), 0o644))
MARKER = os.path.join("pitboard", "copied-from")
CHECK_SECONDS = 3
VERSION_LINE = re.compile(r"^\d+\.\d+\.\d+ \(installed ")
LEFTOVER_SECONDS = 600
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # this version's folder


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def _write_whole(path, data, mode):
    """Write under a temporary name beside the file, then rename (never a half-written file)."""
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def copied_from(home):
    """The version the home's copy came from, or None (a copy from before 0.1.2, or unreadable)."""
    raw = _read(os.path.join(home, MARKER))
    v = raw.decode("utf-8", "replace").strip() if raw else ""
    return v if launch._vkey(v) else None


def write_marker(home, version=__version__):
    _write_whole(os.path.join(home, MARKER), f"{version}\n".encode("utf-8"), 0o644)


def _from_installed_version(root, claude_dir, version):
    cache = os.path.realpath(os.path.join(claude_dir, "plugins", "cache"))
    r = os.path.realpath(root)
    return r.startswith(cache + os.sep) and os.path.basename(r) == version


def _clear_leftovers(home):
    """Temporary folders left by a hook that was killed mid-refresh."""
    now = time.time()
    try:
        names = os.listdir(home)
    except OSError:
        return
    for n in names:
        p = os.path.join(home, n)
        if n.startswith(".refresh-") and os.path.isdir(p):
            try:
                if now - os.stat(p).st_mtime > LEFTOVER_SECONDS:
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass


def _answers(folder, home):
    """(ok, why): does the launcher in `folder` answer its version line against this home?"""
    env = dict(os.environ, PITBOARD_HOME=home)
    try:
        r = subprocess.run([os.path.join(folder, "bin", "pitboard"), "version"], stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=CHECK_SECONDS, env=env)
    except subprocess.TimeoutExpired:
        return False, f"did not answer in {CHECK_SECONDS} s"
    except OSError as e:
        return False, f"could not start ({type(e).__name__})"
    first = (r.stdout.splitlines() or [""])[0]
    if r.returncode != 0 or not VERSION_LINE.match(first):
        return False, f"answered exit {r.returncode}"
    return True, ""


def refresh(home, cfg, root=ROOT, claude_dir=None, version=__version__):
    """Refresh the stable copy if plan 1.16 says so. Returns one log text, or None when nothing was done."""
    claude_dir = claude_dir or launch._claude_dir()
    if cfg.get("self_update") is False or not _from_installed_version(root, claude_dir, version):
        return None
    if version in launch._lines(os.path.join(home, "update", "bad-versions")):
        return None
    new = {rel: _read(os.path.join(root, rel)) for rel, _ in FILES}
    cur = {rel: _read(os.path.join(home, rel)) for rel, _ in FILES}
    if any(v is None for v in new.values()) or any(v is None for v in cur.values()):
        return None                                          # never makes a copy; setup does
    was = copied_from(home)
    if was is not None and launch._vkey(was) > launch._vkey(version):
        return None                                          # never older over newer
    same = cur == new
    if was == version and same:
        return None                                          # up to date
    was_text = was or "before-0.1.2"
    if same:                                                 # the files are already ours: the marker only
        write_marker(home, version)
        return None
    _clear_leftovers(home)
    tmp = tempfile.mkdtemp(prefix=".refresh-", dir=home)
    try:
        for rel, mode in FILES:
            os.makedirs(os.path.join(tmp, os.path.dirname(rel)), exist_ok=True)
            _write_whole(os.path.join(tmp, rel), new[rel], mode)
        ok, why = _answers(tmp, home)
        if not ok:
            # plan 1.19: what this hook did and what it read; another hook may already have refreshed the copy
            return f"stable launcher: this hook left the copy as it was (it read {was_text} when it started): the {version} launcher {why}"
        for rel, mode in FILES:
            dst = os.path.join(home, rel)
            old = _read(dst)
            if old is not None and old != new[rel]:          # back up the replaced copy, never our own
                _write_whole(dst + ".prev", old, mode)
            os.replace(os.path.join(tmp, rel), dst)
        write_marker(home, version)
        return f"stable launcher {was_text} -> {version}, backup kept"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
