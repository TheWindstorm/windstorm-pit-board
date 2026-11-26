"""P102 (G20): one way for a test to start child processes, so that a red says which child it was."""
import subprocess
import tempfile
import time


def run_children(commands, timeout=60, **popen):
    """Start every command at once and wait for each. [] when every child ended with 0; otherwise one line for each
    child that did not: which child, how it ended (its exit code, or that it did not end in the time given, in which
    case it is stopped here) and the last lines of its error stream. Each child's error stream goes to a file of its
    own, so a child that writes much never waits on this reader."""
    started = []
    for cmd in commands:
        err = tempfile.TemporaryFile()
        started.append((subprocess.Popen(cmd, stderr=err, **popen), err))
    end = time.monotonic() + timeout
    out = []
    for n, (p, err) in enumerate(started, 1):
        try:
            code = p.wait(timeout=max(0.0, end - time.monotonic()))
            how = f"ended with exit code {code}"
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            code, how = None, f"did not end in {timeout} s and was stopped"
        if code != 0:
            err.seek(0)
            last = err.read().decode("utf-8", "replace").strip().splitlines()[-5:]
            out.append(f"child {n} of {len(started)} {how}; its last error lines: {' | '.join(last) if last else 'none'}")
        err.close()
    return out
