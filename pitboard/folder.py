"""pitboard setup --folder (plan G18.1, folder mode): Pit Board for the sessions of one folder only.

The plugin with local scope, the Pit Board home if it is missing, and the status line wrapper set in
that folder's .claude/settings.local.json. Never the user's own settings. A record in the folder keeps
the settings file exactly as it was, so the undo can put it back byte for byte. Standard library only.
"""
import json
import os
import subprocess
import time

from . import setup as setup_mod
from . import store

PLUGIN = "windstorm-pit-board@thewindstorm"
RECORD = "pitboard-folder.json"
CLAUDE_LIMIT_SECONDS = 120   # as G21.3


class Refused(Exception):
    """The folder is not one setup --folder may change; nothing was changed."""


def default_home():
    return os.path.join(os.path.expanduser("~"), ".pitboard")


def _paths(folder):
    d = os.path.join(folder, ".claude")
    return d, os.path.join(d, "settings.local.json"), os.path.join(d, RECORD)


def _ps_lines():
    """`pid args` for this user's processes (Linux and macOS both have ps -U -o)."""
    try:
        r = subprocess.run(["ps", "-U", str(os.getuid()), "-o", "pid=,args="], capture_output=True,
                           text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return []
    return r.stdout.splitlines()


def _cwd_of(pid):
    try:
        return os.path.realpath(os.readlink(f"/proc/{pid}/cwd"))
    except OSError:
        pass
    try:   # macOS: no /proc
        r = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], capture_output=True,
                           text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in r.stdout.splitlines():
        if line.startswith("n"):
            return os.path.realpath(line[1:])
    return None


def sessions_in(folder, ps_lines=None, cwd_of=None):
    """Claude Code sessions whose folder is `folder` (P6).

    Counted by the command each process was started as (the first word of its arguments), never by
    the process name: on macOS the process name of a session is its version file (e.g. 2.1.330).
    """
    folder = os.path.realpath(folder)
    found = []
    for line in (ps_lines if ps_lines is not None else _ps_lines()):
        parts = line.split(None, 2)
        if len(parts) < 2 or not parts[0].isdigit():
            continue
        if os.path.basename(parts[1]) != "claude":
            continue
        if (cwd_of or _cwd_of)(int(parts[0])) == folder:
            found.append(int(parts[0]))
    return found


def _load(ls):
    raw = setup_mod._read(ls)
    if raw is None:
        return None, {}
    text = raw.decode("utf-8")
    d = json.loads(text) if text.strip() else {}
    if not isinstance(d, dict):
        raise Refused(f"not a JSON object: {ls}\nNothing changed.")
    return text, d


def _drop(d, home, plugin, strip_env=True):
    """d without Pit Board's entries: the home's wrapper as statusLine, the plugin key, the home in env."""
    d = dict(d)
    if (d.get("statusLine") or {}).get("command") == setup_mod.wrapper_path(home):
        d.pop("statusLine")
    env = dict(d.get("env") or {})
    if strip_env and env.get("PITBOARD_HOME") == home:
        env.pop("PITBOARD_HOME")
        if env:
            d["env"] = env
        else:
            d.pop("env", None)
    ep = dict(d.get("enabledPlugins") or {})
    ep.pop(plugin, None)
    if ep:
        d["enabledPlugins"] = ep
    else:
        d.pop("enabledPlugins", None)
    return d


def _write_atomic(path, text, mode=0o600):
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _claude(args, folder, run=None):
    """Run `claude plugin ...` in the folder; (ok, last line of its output)."""
    run = run or subprocess.run
    try:
        r = run(["claude"] + args, cwd=folder, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                timeout=CLAUDE_LIMIT_SECONDS)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
    return r.returncode == 0, (tail[-1] if tail else "")


def installed_here(folder, plugin=PLUGIN, registry=None):
    """True when Claude Code's plugin registry already has the plugin with local scope for this folder."""
    registry = registry or os.path.join(os.path.expanduser("~"), ".claude", "plugins", "installed_plugins.json")
    try:
        with open(registry, encoding="utf-8") as f:
            entries = (json.load(f).get("plugins") or {}).get(plugin) or []
    except (OSError, ValueError, AttributeError):
        return False
    return any(isinstance(e, dict) and e.get("scope") == "local"
               and os.path.realpath(str(e.get("projectPath", ""))) == os.path.realpath(folder) for e in entries)


def check(folder, home=None, plugin=PLUGIN, sessions=None):
    """The refusals of the folder mode, step 1. Returns (folder, settings text or None, settings dict)."""
    if not os.path.isdir(folder):
        raise Refused(f"no such folder: {folder}")
    folder = os.path.realpath(folder)
    home = home or store.home()
    if folder == os.path.realpath(os.path.expanduser("~")):
        raise Refused(f"{folder} is the home folder.\nLocal scope there reaches every session started from it.\n"
                      "Give the lane its own folder first.")
    n = len(sessions if sessions is not None else sessions_in(folder))
    if n > 1:
        raise Refused(f"{n} Claude Code sessions run in {folder}.\nLocal scope would reach all of them. "
                      "Give this lane its own folder first.")
    _, ls, rec = _paths(folder)
    if os.path.exists(rec):
        raise Refused(f"already set up here: {rec}\nUndo it first.")
    text, d = _load(ls)
    if "statusLine" in d:
        raise Refused("this folder sets its own statusLine; the wrapper wraps only the shared one.\nNothing changed.")
    if (d.get("enabledPlugins") or {}).get(plugin) is not None:
        raise Refused(f"{plugin} is already set here.\nNothing changed.")
    if (d.get("env") or {}).get("PITBOARD_HOME") not in (None, home):
        raise Refused("this folder's settings set another PITBOARD_HOME.\nNothing changed.")
    return folder, text, d


def plan(folder, home=None, plugin=PLUGIN, sessions=None, root=None):
    """The numbered plan for one folder (nothing changes). Raises Refused."""
    home = home or store.home()
    folder, text, d = check(folder, home, plugin, sessions)
    cd, ls, rec = _paths(folder)
    lines = [f"1. record: {rec}", "   create (the folder's settings as they are now, for the undo)",
             f"2. plugin {plugin}, local scope, this folder only",
             "   already installed here: kept" if installed_here(folder, plugin) else "   claude plugin install --scope local"]
    n = 3
    if not (os.path.exists(os.path.join(home, "bin", "pitboard")) and os.path.exists(setup_mod.wrapper_path(home))):
        lines += [f"{n}. Pit Board home: {home}", "   create: config file, stable launcher copy, status line wrapper "
                  "(the user's own status line setting is not touched)"]
        n += 1
    extra = "" if home == default_home() else f", and env.PITBOARD_HOME = {home}"
    lines += [f"{n}. folder status line: {ls}", f"   set statusLine to {setup_mod.wrapper_path(home)}{extra}"
              + ("" if text is None else " (the rest of the file is kept)")]
    return lines


def apply(folder, home=None, plugin=PLUGIN, sessions=None, root=None, run=None):
    """G18.1 folder mode, steps 1 to 6. Returns the lines to print. Raises Refused (nothing changed) or RuntimeError (undone)."""
    home = home or store.home()
    folder, text, d = check(folder, home, plugin, sessions)
    cd, ls, rec = _paths(folder)
    had = os.path.isdir(cd)
    os.makedirs(cd, exist_ok=True)
    _write_atomic(rec, json.dumps({"plugin": plugin, "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                   "settings_local_before": text, "claude_dir_existed": had, "home": home},
                                  indent=1) + "\n")
    out = []
    try:
        if installed_here(folder, plugin):
            out.append(f"plugin {plugin}: already installed for {folder}; kept")
        else:
            ok, tail = _claude(["plugin", "install", plugin, "--scope", "local"], folder, run)
            if not ok:
                raise RuntimeError(f"claude plugin install failed: {tail}")
            out.append(f"plugin {plugin}: installed for {folder} only")
        if not (os.path.exists(os.path.join(home, "bin", "pitboard")) and os.path.exists(setup_mod.wrapper_path(home))):
            items = [i for i in setup_mod.plan_minimal(home=home, root=root) if i.name != "status line setting"]
            setup_mod.apply(items)
            out.append(f"made the Pit Board home {home}; the user's own status line setting is not touched")
        _, now = _load(ls)
        now["statusLine"] = {"type": "command", "command": setup_mod.wrapper_path(home), "padding": 0,
                             "refreshInterval": 5}
        if home != default_home():   # the home rides in the folder's settings, so any restart keeps it
            now.setdefault("env", {})["PITBOARD_HOME"] = home
        _write_atomic(ls, json.dumps(now, indent=2) + "\n")
        out.append(f"folder status line: {ls}")
    except Exception as e:
        undo(folder, run=run)
        raise RuntimeError(f"{e}; undone")
    out += [f"Pit Board is on in {folder} only.", "A session started (or resumed) there picks it up."]
    return out


def undo(folder, run=None, envhome=None):
    """Uninstall the plugin from the folder and put its settings back (G18.1 folder mode). Returns the lines to print."""
    folder = os.path.realpath(folder)
    cd, ls, rec = _paths(folder)
    try:
        r = json.loads(setup_mod._read(rec).decode("utf-8"))
    except (AttributeError, ValueError) as e:
        raise Refused(f"no readable record at {rec}: setup --folder did not set up here ({e})")
    plugin, before = r["plugin"], r["settings_local_before"]
    home = r.get("home") or envhome or store.home()
    out = []
    ok, tail = _claude(["plugin", "uninstall", plugin, "--scope", "local"], folder, run)
    out.append(f"plugin {plugin}: " + ("removed from this folder" if ok else f"uninstall said: {tail}"))
    _, now = _load(ls)
    old = json.loads(before) if before and before.strip() else {}
    keep_env = (old.get("env") or {}).get("PITBOARD_HOME") == home   # the person's own, set before setup
    mine = _drop(now, home, plugin, not keep_env)
    if mine == _drop(old, home, plugin, not keep_env):
        if before is None:
            if os.path.exists(ls):
                os.remove(ls)
            how = "removed (there was none before)"
        else:
            _write_atomic(ls, before)
            how = "put back byte for byte"
    else:
        _write_atomic(ls, json.dumps(mine, indent=2) + "\n")
        how = "Pit Board's entries removed; other changes made since setup are kept"
    os.remove(rec)
    if not r.get("claude_dir_existed", True) and os.path.isdir(cd) and not os.listdir(cd):
        os.rmdir(cd)
    out.append(f"{ls}: {how}")
    out += [f"Pit Board is off in {folder}.", f"Its asks stay in {home}.",
            "Restart or resume the session there to drop the hooks."]
    return out
