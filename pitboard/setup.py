"""pitboard setup (plan G18.1): show a numbered plan; change nothing without --apply.

Milestone 1 builds `--minimal`: the config file, the stable launcher copy (G21.4) and the
status line wrapper (G10.5). Every file it changes keeps a `.bak-<timestamp>` copy.
Standard library only.
"""
import json
import os
import shlex
import stat
import time

from . import __version__, leave, stablecopy, store

MARK = "# pitboard-original-command: "
WRAPPER_NAME = "statusline.sh"
STATUS_CAP_SECONDS = 1   # G10.5: past this, the operator's own line prints alone


def claude_settings_path():
    return os.path.join(os.path.expanduser("~"), ".claude", "settings.json")


def _root():
    """The running version's folder (it holds bin/pitboard and pitboard/launch.py)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def _stamp():
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime())


def wrapper_path(home=None):
    return os.path.join(home or store.home(), WRAPPER_NAME)


def original_from_wrapper(path):
    """The operator's own status line command, as recorded in our wrapper (None if none)."""
    raw = _read(path)
    if raw is None:
        return None
    for line in raw.decode("utf-8", "replace").splitlines():
        if line.startswith(MARK):
            try:
                v = json.loads(line[len(MARK):])
            except ValueError:
                return None
            return v if isinstance(v, str) and v else None
    return None


def wrapper_text(original, home):
    """G10.5: run the operator's status line and Pit Board's segment with the same input, and
    print the segment first: before a one-line status line, joined with ' · ', or on its own
    first line above a status line of several lines, so it is never pushed past the right edge.
    Pit Board's part runs under a cap (timeout, or gtimeout on macOS, when either exists); on an
    error or the cap only the operator's line is printed (G10.4)."""
    launcher = os.path.join(home, "bin", "pitboard")
    lines = [
        "#!/bin/sh",
        "# Written by pitboard setup (plan G10.5). Runs your own status line and Pit Board's segment; prints the segment first.",
        MARK + json.dumps(original or ""),
        "in=$(cat)",
        "SH=sh; command -v bash >/dev/null 2>&1 && SH=bash",
    ]
    if original:
        lines.append(f"own=$(printf '%s' \"$in\" | \"$SH\" -c {shlex.quote(original)} 2>/dev/null)")
    else:
        lines.append("own=")
    lines += [
        "CAP=",
        f"if command -v timeout >/dev/null 2>&1; then CAP='timeout {STATUS_CAP_SECONDS}'; "
        f"elif command -v gtimeout >/dev/null 2>&1; then CAP='gtimeout {STATUS_CAP_SECONDS}'; fi",
        f"pb=$(printf '%s' \"$in\" | PITBOARD_HOME={shlex.quote(home)} $CAP {shlex.quote(launcher)} status 2>/dev/null) || pb=",
        "nl='\n'",
        'if [ -n "$own" ] && [ -n "$pb" ]; then',
        '  case "$own" in *"$nl"*) printf \'%s\\n%s\' "$pb" "$own" ;; *) printf \'%s · %s\' "$pb" "$own" ;; esac',
        "else printf '%s%s' \"$own\" \"$pb\"; fi",
        "",
    ]
    return "\n".join(lines)


class Item:
    def __init__(self, name, path, action, content=None, mode=0o600, json_obj=None, close=None, name_only=False):
        self.name, self.path, self.action = name, path, action
        self.content, self.mode, self.json_obj = content, mode, json_obj
        self.close, self.name_only = close, name_only     # P41: paths to close; a folder only named, never changed

    def as_dict(self):
        return {"item": self.name, "path": self.path, "action": self.action}


def _file_item(name, path, content, mode):
    old = _read(path)
    if old == content:
        action = "keep (already up to date)"
    elif old is None:
        action = "create"
    else:
        action = "replace (backup kept)"
    return Item(name, path, action, content, mode)


def mode_text(path):
    """P25: what setup does to the settings file's mode and its backup, said before it is done (setup writes it 600).
    Returns (words for the action line, more lines): short lines, so the CLI's width cut never hides them."""
    try:
        now = os.stat(path).st_mode & 0o777
    except FileNotFoundError:
        return "no settings file before", ["the file is made private (600); there is nothing to back up"]
    if now == 0o600:
        return "backup kept", []
    return "backup kept", [f"the file is {now:o} now and is written private (600); the backup keeps {now:o}",
                           f"uninstall puts {now:o} back only when it puts the file back byte for byte"]


def _open_mode(path):
    """The mode when another account can write it (group or other write), else None. A link is never followed."""
    try:
        st = os.lstat(path)
    except OSError:
        return None
    return st.st_mode & 0o777 if not stat.S_ISLNK(st.st_mode) and st.st_mode & 0o022 else None


def own_open(home):
    """P41: Pit Board's own entries (the home is Pit Board's alone, P40) that another account can write."""
    if not os.path.isdir(home) or os.path.islink(home):
        return []
    found = [home] if _open_mode(home) is not None else []
    for top, dirs, files in os.walk(home):
        found += [p for p in (os.path.join(top, n) for n in sorted(dirs) + sorted(files)) if _open_mode(p) is not None]
    return found


def way_open(home, settings_path):
    """P41: folders on the way that are not Pit Board's and that it cannot know it made: the folder above the settings
    file, and the folder above a home that is not the default one. Named with the command, never changed."""
    way = [os.path.dirname(os.path.abspath(settings_path))]
    if os.path.abspath(home) != os.path.join(os.path.expanduser("~"), ".pitboard"):
        way.append(os.path.dirname(os.path.abspath(home)))
    return [(w, _open_mode(w)) for w in dict.fromkeys(way) if _open_mode(w) is not None]


def closing_items(home, settings_path):
    """P41 (the family's rule 28, a file is only as closed as the folders above it)."""
    items = []
    own = own_open(home)
    if own:
        rel = [f"{os.path.relpath(p, home) if p != home else '.'} ({_open_mode(p):o})" for p in own]
        items.append(Item("Pit Board's own, open to other accounts", home,
                          "\n".join(["would close: group and other write taken off"] + rel), close=own))
    for w, m in way_open(home, settings_path):
        items.append(Item("a folder on the way, not Pit Board's", w,
                          f"open to other accounts ({m:o}); setup does not change it\nto close it: chmod go-w {shlex.quote(w)}",
                          name_only=True))
    return items


def plan_minimal(home=None, settings_path=None, root=None):
    """The --minimal items, in order (G18.1)."""
    home = home or store.home()
    settings_path = settings_path or claude_settings_path()
    root = root or _root()
    items = []

    cfg_path = os.path.join(home, "config.json")
    if os.path.exists(cfg_path):
        items.append(Item("config file", cfg_path, "keep (already there)"))
    else:
        body = (json.dumps(store.DEFAULTS, indent=2) + "\n").encode("utf-8")
        items.append(Item("config file", cfg_path, "create with the defaults", body, 0o600))

    for rel, mode in stablecopy.FILES:                  # the launcher and leave.py (G21.4, G18.3)
        src = _read(os.path.join(root, rel))
        if src is None:
            raise FileNotFoundError(f"the running version has no {rel}: {root}")
        items.append(_file_item("stable launcher copy", os.path.join(home, rel), src, mode))
    items.append(_file_item("stable launcher copy", os.path.join(home, stablecopy.MARKER),
                            f"{__version__}\n".encode("utf-8"), 0o644))       # copied-from (G21.4)

    wpath = wrapper_path(home)
    try:
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
    except FileNotFoundError:
        settings = {}
    if not isinstance(settings, dict):
        raise ValueError(f"not a JSON object: {settings_path}")
    sl = settings.get("statusLine")
    current = sl.get("command") if isinstance(sl, dict) else None
    if current == wpath:
        original = original_from_wrapper(wpath)       # already wrapped: keep the recorded original
    else:
        original = current if isinstance(current, str) and current.strip() else None
    items.append(_file_item("status line wrapper", wpath, wrapper_text(original, home).encode("utf-8"), 0o755))

    if current == wpath:
        items.append(Item("status line setting", settings_path, "keep (already points at the wrapper)"))
    else:
        new = dict(settings)
        new_sl = dict(sl) if isinstance(sl, dict) else {}
        new_sl.update({"type": "command", "command": wpath})
        new["statusLine"] = new_sl
        was = f"was {json.dumps(current)}" if current else "no status line before"
        said, more = mode_text(settings_path)
        items.append(Item("status line setting", settings_path,
                          "\n".join([f"set statusLine.command to the wrapper ({was}; {said})"] + more), json_obj=new))
    return items + closing_items(home, settings_path)


def note(home, settings=None, folder=None, backup=None, made=None):
    """G18.3: the record of what setup did, `setup-record.json` in the home, for `pitboard uninstall`.
    settings = (path, bytes before or None, mode before or None, bytes after): the earliest `before` stays while the
    file is still what Pit Board last wrote. backup = the name of the backup setup made of it: the census counts only
    the backups listed here, because other tools name theirs the same way (P29). A record that cannot be read is never
    written over."""
    path = os.path.join(home, leave.SETUP_RECORD)
    try:
        rec = leave.read_object(path) or {}
    except leave.Unread:
        return
    rec["version"] = __version__
    if settings:
        spath, before, mode, after = settings
        files = [e for e in rec.get("files") or [] if isinstance(e, dict)]
        old = next((e for e in files if e.get("path") == spath), None)
        if old and before is not None and old.get("after_sha256") == leave.sha256(before):
            entry = dict(old)                           # unchanged since Pit Board wrote it: the first before stays
        else:
            entry = {"path": spath, "before": None if before is None else before.decode("utf-8"),
                     "before_mode": mode}
        entry["after_sha256"] = leave.sha256(after)
        made = [b for b in (old or {}).get("backups") or [] if isinstance(b, str)]
        entry["backups"] = made + ([os.path.basename(backup)] if backup and os.path.basename(backup) not in made else [])
        rec["files"] = [e for e in files if e.get("path") != spath] + [entry]
    if folder:
        folders = [f for f in rec.get("folders") or [] if isinstance(f, str)]
        rec["folders"] = folders + ([folder] if folder not in folders else [])
    if made:                                                  # P40: what setup made in the home, for uninstall
        had = [m for m in rec.get("made") or [] if isinstance(m, str)]
        rec["made"] = had + [m for m in made if m not in had]
    os.makedirs(home, exist_ok=True)
    leave.write_atomic(path, json.dumps(rec, indent=1, ensure_ascii=False) + "\n")


def apply(items, home=None):
    """Do the plan. Every file that exists and changes keeps a .bak-<timestamp> copy. A changed settings file is
    noted in the home's setup record (G18.3)."""
    stamp = _stamp()
    done = []
    wrapper = next((it.path for it in items if it.name == "status line wrapper"), None)
    home = home or (os.path.dirname(wrapper) if wrapper else None)
    for it in items:
        if it.action.startswith("keep") or it.name_only:
            continue
        if it.close is not None:                         # P41: Pit Board's own, closed where they are
            for p in it.close:
                m = _open_mode(p)
                if m is not None:
                    os.chmod(p, m & ~0o022)
            it.action = it.action.replace("would close", "closed", 1)
            done.append(it)
            continue
        os.makedirs(os.path.dirname(it.path), exist_ok=True)
        new_here = not os.path.exists(it.path)
        before = leave.read_bytes(it.path) if it.json_obj is not None else None
        before_mode = os.stat(it.path).st_mode & 0o777 if before is not None else None
        bak = None
        if os.path.exists(it.path):
            bak, n = f"{it.path}.bak-{stamp}", 1
            while os.path.lexists(bak):                  # never over an earlier backup
                n += 1
                bak = f"{it.path}.bak-{stamp}-{n}"
            st = os.stat(it.path)                        # P41: opened new at the mode the file had (P25), times kept
            leave.write_new(bak, leave.read_bytes(it.path), st.st_mode & 0o777)
            os.utime(bak, ns=(st.st_atime_ns, st.st_mtime_ns))
        if it.json_obj is not None:
            content = (json.dumps(it.json_obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            mode = 0o600
        else:
            content, mode = it.content, it.mode
        leave.write_atomic(it.path, content, mode)       # P41: opened new at its mode, never narrowed after
        done.append(it)
        if new_here and home and it.json_obj is None and os.path.dirname(it.path) == home:
            note(home, made=[os.path.basename(it.path)])       # P40: config.json and the wrapper, by record
        if it.json_obj is not None and home:
            note(home, settings=(it.path, before, before_mode, content), backup=bak)
    return done


def describe(items, applied=None):
    lines = []
    for n, it in enumerate(items, 1):
        lines.append(f"{n}. {it.name}: {it.path}")
        lines.extend(f"   {ln}" for ln in it.action.split("\n"))
    if applied is None:
        lines.append("Nothing changed. Run again with --apply to do it.")
    else:
        lines.append(f"Done: {len(applied)} change(s)." if applied else "Nothing to change.")
    return "\n".join(lines)
