"""Pit Board launcher (plan G21.4): pick the version folder to run, then call its cli.main().

This file must stay tiny and import nothing from Pit Board: the stable copy in
$PITBOARD_HOME/pitboard/launch.py runs alone, and an older copy of it must always be
able to run the newest code. It only picks a folder and calls cli.main().
"""
import json
import os
import re
import sys

PLUGIN = "windstorm-pit-board"
VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _home():
    return os.environ.get("PITBOARD_HOME") or os.path.join(os.path.expanduser("~"), ".pitboard")


def _claude_dir():
    return os.path.join(os.path.expanduser("~"), ".claude")


def _lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip()]
    except OSError:
        return []


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
    """installed_plugins.json entries for Pit Board, the user-scope install first: [(path, version)]."""
    try:
        with open(os.path.join(claude_dir, "plugins", "installed_plugins.json"), encoding="utf-8") as f:
            plugins = json.load(f).get("plugins", {})
    except (OSError, ValueError, AttributeError):
        return []
    rows = []
    for name, entries in plugins.items() if isinstance(plugins, dict) else ():
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
            folder = os.path.join(base, v)
            if _vkey(v) and not os.path.exists(os.path.join(folder, ".orphaned_at")):
                out.setdefault(v, folder)
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
    good, bad = set(_lines(os.path.join(upd, "good-versions"))), set(_lines(os.path.join(upd, "bad-versions")))
    pin = (_lines(os.path.join(upd, "pin")) or [None])[0]
    installed = _installed(claude_dir)
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
    if _runnable(own_root) and os.path.basename(own_root) not in bad:               # 5
        return own_root, 5
    for path, v in sorted(installed, key=lambda r: _vkey(r[1]) or (-1,), reverse=True):  # 6
        if v not in bad and _runnable(path):                # the highest version, never the first entry (P8)
            return path, 6
    return None, 7


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    is_hook = bool(argv) and argv[0] == "hook"
    own = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        root, _ = choose(own_root=own, skip_pin=argv[:1] == ["self-update"])
    except Exception:  # noqa: BLE001 - a hook never breaks the session (INV6)
        if is_hook:
            return 0
        raise
    if root is None:
        if is_hook:
            return 0
        sys.stderr.write("pitboard: no installed version found\n")
        return 1
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
