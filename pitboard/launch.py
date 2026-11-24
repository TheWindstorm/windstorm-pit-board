"""Pit Board launcher (plan G21.4): pick the version folder to run, then call its cli.main().

This file must stay tiny and import nothing from Pit Board: the stable copy in
$PITBOARD_HOME/pitboard/launch.py runs alone, and an older copy of it must always be
able to run the newest code. It only picks a folder and calls cli.main(), with one exception
(plan 1.28): `uninstall` runs leave.py beside it, so what stays on the computer can take itself off.

Its first act is the Python floor check (G21.15). This file must stay readable by Python 3.6's grammar, so an
older interpreter reaches that check instead of stopping on a syntax error.
"""
import json
import os
import re
import sys
import time
sys.dont_write_bytecode = True    # P37, rule 23: no .pyc in the version folder, which is Claude Code's
PLUGIN = "windstorm-pit-board"
VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
FLOOR = (3, 9)          # G21.15: the oldest Python Pit Board runs on; rule 4, the README and CI name the same


def _found():
    return tuple(sys.version_info[:3])


def floor_refusal(argv):
    """G21.15: None when this Python is new enough. Otherwise (exit code, stdout text, stderr text), so the caller
    stops before it reads or writes anything. 3.8 is refused: no zoneinfo, so it showed wrong times with no error."""
    found = _found()
    if found[:2] >= FLOOR:
        return None
    want, got = "{}.{}".format(*FLOOR), ".".join(str(n) for n in found)
    cmd = argv[0] if argv else ""
    if cmd == "status":                                   # G10.4's one exception: a short true line
        return 0, "Pit Board needs Python {} or newer, found {}".format(want, got), ""
    line = "Pit Board needs Python {} or newer; found {} at {}\n".format(want, got, sys.executable or "python")
    if cmd == "hook":                                     # a hook never breaks the session (rule 6)
        return 0, "", line
    return 10, "", line + "pitboard: install Python {} or newer, or put one first on PATH as python3\n".format(want)


def floor_stop(refusal, stdout=None, stderr=None):
    code, out, err = refusal
    (stdout or sys.stdout).write(out)
    (stderr or sys.stderr).write(err)
    return code


def _home():
    return os.environ.get("PITBOARD_HOME") or os.path.join(os.path.expanduser("~"), ".pitboard")


def _claude_dir():
    return os.path.join(os.path.expanduser("~"), ".claude")


UNREAD = []             # P19 (plan 1.29): the reads the last choose() could not make, as (path, error name)
REMOVED = "Pit Board was removed by Claude Code"


def _lines(path):
    return _read(path) or []


def _read(path):
    """Three answers (P19): the lines (yes), [] when the file is missing (no), None when it could not be read."""
    try:
        with open(path, encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip()]
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError) as e:
        UNREAD.append((path, type(e).__name__))
        return None


def _orphaned(folder):
    return os.path.exists(os.path.join(folder, ".orphaned_at"))


def _self_update(home):
    env = os.environ.get("PITBOARD_SELF_UPDATE")
    if env in ("0", "1"):
        return env == "1"
    try:
        with open(os.path.join(home, "config.json"), encoding="utf-8") as f:
            v = json.load(f).get("self_update", True)
        return v is not False
    except (OSError, ValueError, AttributeError):
        return True


def _runnable(root):
    return bool(root) and os.path.isfile(os.path.join(root, "pitboard", "cli.py"))


def _vkey(v):
    m = VERSION.match(v or "")
    return tuple(int(x) for x in m.groups()) if m else None


def _installed(claude_dir):
    return _registry(claude_dir) or []


def _registry(claude_dir):
    """installed_plugins.json entries for Pit Board, the user-scope install first: [(path, version)]. Three answers
    (P19): [] when the registry is missing, None when it cannot be opened, decoded or is not an object of plugins."""
    path = os.path.join(claude_dir, "plugins", "installed_plugins.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as e:
        UNREAD.append((path, type(e).__name__))
        return None
    plugins = data.get("plugins", {}) if isinstance(data, dict) else None
    if not isinstance(plugins, dict):
        UNREAD.append((path, "not a JSON object with plugins"))
        return None
    rows = []
    for name, entries in plugins.items():
        if name.split("@", 1)[0] != PLUGIN or not isinstance(entries, list):
            continue
        for e in entries:
            if isinstance(e, dict) and isinstance(e.get("installPath"), str):
                rows.append((e.get("scope") != "user", e["installPath"], str(e.get("version") or "")))
    rows.sort(key=lambda r: r[0])
    return [(p, v) for _, p, v in rows]


def _cached(claude_dir):
    """Version folders in the plugin cache: {version: folder}, skipping orphaned ones."""
    out = {}
    cache = os.path.join(claude_dir, "plugins", "cache")
    try:
        markets = os.listdir(cache)
    except OSError:
        return out
    for m in markets:
        base = os.path.join(cache, m, PLUGIN)
        try:
            names = os.listdir(base)
        except OSError:
            continue
        for v in names:
            if _vkey(v) and not _orphaned(os.path.join(base, v)):
                out.setdefault(v, os.path.join(base, v))
    return out


def choose(home=None, claude_dir=None, own_root=None, skip_pin=False):
    """G21.4: (folder, step) for the version to run, or (None, 7).

    A version in update/bad-versions is never picked (G21.10), except by step 2:
    with self_update off the operator's own install runs whatever its version (G21.12).
    skip_pin (for `self-update`, plan 1.18): start at step 2, so a pin to a version without
    self-update can still be released."""
    home = home or _home()
    claude_dir = claude_dir or _claude_dir()
    upd = os.path.join(home, "update")
    del UNREAD[:]
    good, bad, pins = (_read(os.path.join(upd, n)) for n in ("good-versions", "bad-versions", "pin"))
    installed = _registry(claude_dir)
    if UNREAD:      # P19: could not be read is not "none": do not move to another version on this pass
        if _runnable(own_root) and not _orphaned(own_root):
            return own_root, 5
        return None, 7
    good, bad, pin = set(good), set(bad), (pins or [None])[0]
    cached = _cached(claude_dir)

    if pin and not skip_pin and pin not in bad and _runnable(cached.get(pin)):      # 1
        return cached[pin], 1
    if not _self_update(home):                                                      # 2
        for path, _ in installed:
            if _runnable(path):
                return path, 2
    for path, v in installed:                                                       # 3
        if v in good and v not in bad and _runnable(path):
            return path, 3
    for v in sorted(cached, key=_vkey, reverse=True):                               # 4
        if v in good and v not in bad and _runnable(cached[v]):
            return cached[v], 4
    if _runnable(own_root) and os.path.basename(own_root) not in bad and not _orphaned(own_root):   # 5
        return own_root, 5
    for path, v in sorted(installed, key=lambda r: _vkey(r[1]) or (-1,), reverse=True):  # 6
        if v not in bad and _runnable(path):                # the highest version, never the first entry (P8)
            return path, 6
    return None, 7


def _log(hook, what):
    """One line in logs/pitboard.log when no folder runs to write it (P19). Best effort: never fails a hook."""
    try:
        with open(os.path.join(_home(), "logs", "pitboard.log"), "a", encoding="utf-8") as f:
            f.write("{} {} - {}\n".format(time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()), hook, what))
    except OSError:
        pass


def _leave(argv):
    """G18.3 point 9: run leave.py beside this file (the home's, if this folder is orphaned); None if there is none."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(_home(), "pitboard", "leave.py") if _orphaned(os.path.dirname(here)) else \
        os.path.join(here, "leave.py")
    try:
        with open(path, encoding="utf-8") as f:
            code = compile(f.read(), path, "exec")
    except FileNotFoundError:
        return None
    ns = {"__name__": "pitboard_leave", "__file__": path}
    exec(code, ns)
    return ns["main"](list(argv[1:]))


def _copy_cmd(sub):
    home, user = _home(), os.path.expanduser("~")      # the command only while the copy that runs it is there
    shown = os.path.join("~" + home[len(user):] if home.startswith(user + os.sep) else home, "bin", "pitboard")
    return " · run {} {}".format(shown, sub) if os.path.isfile(os.path.join(home, "bin", "pitboard")) else ""


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    refusal = floor_refusal(argv)                      # G21.15: the first act, before anything is read or written
    if refusal:
        return floor_stop(refusal)
    if argv[:1] == ["uninstall"]:                      # plan 1.28: the one exception, no orphaned code runs
        code = _leave(argv)
        if code is not None:
            return code
    is_hook = bool(argv) and argv[0] == "hook"
    own = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        root, step = choose(own_root=own, skip_pin=argv[:1] == ["self-update"])
    except Exception:  # noqa: BLE001 - a hook never breaks the session (INV6)
        if is_hook:
            return 0
        raise
    unread = "; ".join("{} ({})".format(p, e) for p, e in UNREAD)
    if root is None:
        if unread:                                     # P19: nothing run, and say which read failed
            if is_hook:
                _log(argv[1] if len(argv) > 1 else "hook", "launcher could not read " + unread + "; nothing run")
                return 0
            if argv[:1] == ["status"]:                 # plan 1.31: an error is never shown as nothing (rule 6)
                sys.stdout.write("Pit Board cannot read its files" + _copy_cmd("version"))
                return 0
            sys.stderr.write("pitboard: could not read {}; nothing run\n".format(unread))
            return 1
        reg = os.path.join(_claude_dir(), "plugins", "installed_plugins.json")
        removed = os.path.isfile(reg) and _registry(_claude_dir()) == []   # read, no row: Claude Code's uninstall
        if is_hook:
            if removed:
                _log(argv[1] if len(argv) > 1 else "hook", "Pit Board was removed by Claude Code; nothing done")
            return 0
        if removed and argv[:1] == ["status"]:
            sys.stdout.write(REMOVED + _copy_cmd("uninstall"))
            return 0
        sys.stderr.write("pitboard: no installed version found\n" + (REMOVED + _copy_cmd("uninstall") + "\n" if removed else ""))
        return 1
    os.environ["PITBOARD_LAUNCH_STEP"] = str(step)     # P15: each hook log line names the step that picked it
    os.environ.update(PITBOARD_LAUNCH_UNREAD=unread) if unread else os.environ.pop("PITBOARD_LAUNCH_UNREAD", None)  # P19, never stale
    sys.path.insert(0, root)
    for name in [n for n in sys.modules if n == "pitboard" or n.startswith("pitboard.")]:
        del sys.modules[name]
    try:
        from pitboard import cli
    except Exception:  # noqa: BLE001
        if is_hook:
            return 0
        raise
    sys.argv = [sys.argv[0]] + list(argv)
    return cli.main()


if __name__ == "__main__":
    sys.exit(main())
