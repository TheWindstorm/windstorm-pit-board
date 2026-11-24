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

from . import __version__, launch, leave, stablecopy, store

MARK = "# pitboard-original-command: "
WRAPPER_NAME = "statusline.sh"
STATUS_CAP_SECONDS = 1   # G10.5: past this, the operator's own line prints alone
# P52: the cap, needing no program the machine may lack: no single quote in it, so it can be quoted for the shell.
CAP_RUNNER = ("import os,signal,subprocess,sys;p=subprocess.Popen(sys.argv[2:],start_new_session=True,stdout=subprocess.PIPE)\n"
              "try:\n o=p.communicate(timeout=float(sys.argv[1]))[0]\nexcept subprocess.TimeoutExpired:\n"
              " os.killpg(p.pid,signal.SIGKILL);sys.exit(124)\nsys.stdout.buffer.write(o);sys.exit(p.returncode)")


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


def segment_read_lines(home):
    """P54 (measured on a real Mac: a redraw with Pit Board took 130 to 150 ms under Apple's python3, the person's own
    script 11 ms): the wrapper shows the segment Pit Board last kept for this session (state/<session id>.seg, written
    by `status`) without starting Python, when all of these hold: the session id and the session name it finds in the
    input are the ones the file was kept for (the id: the text after the one '"session_id":"' up to the next quote; the
    name: the JSON text of the one '"session_name":"' up to its first quote not escaped, kept escaped as it came);
    NO_COLOR is as it was; the clock is before the time the text stays true until; and each file the file names
    is there or not as it was and, if there, strictly older than the file (the file's time is the moment Pit Board started,
    before it read anything; a file of the same time counts as changed); the clock is not before that moment (a clock
    that went back makes it stale). Existence is tested by itself: dash says a file is not newer than a missing one,
    bash says it is. Anything else, a file that is missing, unreadable or not of this shape included, runs Pit Board
    as before, handing it the session id and name it found (PITBOARD_WRAPPER_SID, PITBOARD_WRAPPER_NAME), which the
    file then stores as they are: one text decides. On that road the wrapper starts `date` and nothing more beyond what
    it starts anyway (`cat` for the input, and the person's own status line)."""
    return [
        f"H={shlex.quote(home)}",
        "sid=; nm=; nok=; hit=; ok=; pb=",
        "case $in in *'\"session_id\":\"'*'\"session_id\":\"'*) ;; *'\"session_id\":\"'*) sid=${in#*'\"session_id\":\"'}; "
        "sid=${sid%%'\"'*} ;; esac",
        "case $sid in *[!a-z0-9-]*) sid= ;; esac",
        "case $in in *'\"session_name\":\"'*'\"session_name\":\"'*) ;; *'\"session_name\":\"'*) "
        "r=${in#*'\"session_name\":\"'}",
        "  while c=${r%%'\"'*}; [ \"$c\" != \"$r\" ]; do nm=$nm$c; r=${r#*'\"'}; b=${c##*[!\\\\]}",
        "    [ $((${#b} % 2)) = 1 ] || { nok=1; break; }; nm=$nm'\"'; done ;; *) nok=1 ;; esac",
        'f="$H/state/$sid.seg"',
        'if [ -n "$sid" ] && [ -n "$nok" ] && [ -f "$f" ]; then',
        '  { IFS= read -r h && IFS= read -r knm && IFS= read -r seg && n=0 && ok=1 &&',
        '    while IFS= read -r d; do n=$((n+1)); case $d in',
        "      '+ '*) { [ -e \"${d#+ }\" ] && [ \"$f\" -nt \"${d#+ }\" ]; } || ok= ;;",
        "      '- '*) [ ! -e \"${d#- }\" ] || ok= ;;",
        "      *) ok= ;; esac; done; } < \"$f\" 2>/dev/null",
        '  set -f; set -- $h; set +f; p=0; [ -n "${NO_COLOR+x}" ] && p=1',
        '  if [ -n "$ok" ] && [ "$1 $2" = "pitboard-seg 1" ] && [ "$6" = "$p" ] && [ "$7" = "$n" ] && [ "$knm" = "$nm" ]; then',
        '    now=$(date +%s); [ "$now" -lt "$4" ] 2>/dev/null && [ "$now" -ge "$5" ] 2>/dev/null && pb=$seg && hit=1',
        "  fi",
        "fi",
        '[ -n "$sid" ] && [ -n "$nok" ] && export PITBOARD_WRAPPER_SID="$sid" PITBOARD_WRAPPER_NAME="$nm"',
    ]


def wrapper_text(original, home):
    """G10.5: run the operator's status line and Pit Board's segment with the same input, and
    print the segment first: before a one-line status line, joined with ' · ', or on its own
    first line above a status line of several lines, so it is never pushed past the right edge.
    Pit Board's part runs under a cap (P52): a few lines of python3, the one program Pit Board needs anyway, that start
    it in its own process group and stop the whole group at the cap, so a child it left behind cannot hold the line
    either. Before, the cap was timeout or gtimeout when either existed and none at all on a machine with neither
    (macOS 13 as it comes), and a child left behind held the line past it. On an error or the cap only the operator's
    line is printed (G10.4). The input is read whole, a trailing newline included (P53), and handed on to both byte for
    byte."""
    launcher = os.path.join(home, "bin", "pitboard")
    lines = [
        "#!/bin/sh",
        "# Written by pitboard setup (plan G10.5). Runs your own status line and Pit Board's segment; prints the segment first.",
        MARK + json.dumps(original or ""),
        "in=$(cat; printf x); in=${in%x}",
        "SH=sh; command -v bash >/dev/null 2>&1 && SH=bash",
    ]
    if original:
        lines.append(f"own=$(printf '%s' \"$in\" | \"$SH\" -c {shlex.quote(original)} 2>/dev/null)")
    else:
        lines.append("own=")
    lines += segment_read_lines(home) + [
        f"cap() {{ python3 -I -c {shlex.quote(CAP_RUNNER)} {STATUS_CAP_SECONDS} \"$@\"; }}",
        f"[ -n \"$hit\" ] || pb=$(export PITBOARD_HOME={shlex.quote(home)}; printf '%s' \"$in\" | cap {shlex.quote(launcher)} status 2>/dev/null) || pb=",
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


def _other_members(gid, owner):
    """The accounts other than the owner and root in group `gid`: its member list and every account whose primary group
    it is. None when that cannot be read. Root can write anything; naming a folder for it says nothing (P45, seen on a
    Mac, where a new folder under /tmp takes the group wheel)."""
    import grp
    import pwd
    try:
        uids = {pwd.getpwnam(n).pw_uid for n in grp.getgrgid(gid).gr_mem}
        uids |= {p.pw_uid for p in pwd.getpwall() if p.pw_gid == gid}
    except (KeyError, OSError):
        return None
    return uids - {owner, 0}                              # P45: root (number 0) is the administrator, never "another"


def _groups(uid):
    """The group numbers of account `uid` (unsigned, as stat gives them), or None when they cannot be read. P44: on a
    Mac some accounts carry group 4294967294 ("nobody", -2 without its sign) and os.getgrouplist raises OverflowError
    on it; the same number given signed answers."""
    import pwd
    try:
        p = pwd.getpwuid(uid)
    except (KeyError, OSError):
        return None
    for gid in (p.pw_gid, p.pw_gid - 2 ** 32 if p.pw_gid >= 2 ** 31 else None):
        if gid is None:
            continue
        try:
            return {g % 2 ** 32 for g in os.getgrouplist(p.pw_name, gid)} | {p.pw_gid}
        except (OverflowError, OSError, ValueError):
            continue
    return None


def _passes(uid, groups, st, bits):
    """Account `uid` (None: an account in none of the groups) has `bits` (x=1, wx=3) on the folder `st`."""
    if uid is not None and uid == st.st_uid:
        return st.st_mode >> 6 & bits == bits
    if uid is not None and st.st_gid in groups:
        return st.st_mode >> 3 & bits == bits
    return st.st_mode & bits == bits


def who_can_write(path):
    """P41, the family's rule 28 (WHEN A PERSON'S FOLDER IS NAMED): why another account can really reach and write
    the folder at `path`, or None. Write: writable by others, or by its group when the group has a member other than
    the owner. Reach: every folder above lets that account pass. A link is never followed."""
    try:
        st = os.lstat(path)
        if stat.S_ISLNK(st.st_mode) or not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)) \
                or not st.st_mode & 0o022:
            return None
        if stat.S_ISDIR(st.st_mode) and st.st_mode & stat.S_ISVTX:   # sticky (/tmp): no other account replaces ours
            return None
        bits = 3 if stat.S_ISDIR(st.st_mode) else 2       # P47: a file is written with w alone
        above, p = [], os.path.dirname(os.path.abspath(path))
        while True:
            above.append(os.stat(p))
            if os.path.dirname(p) == p:
                break
            p = os.path.dirname(p)
    except OSError:
        return None
    if _passes(None, set(), st, bits) and all(_passes(None, set(), a, 1) for a in above):
        return "any account can reach and write it"
    if st.st_mode & 0o020 and (bits == 2 or st.st_mode & 0o010):
        members = _other_members(st.st_gid, st.st_uid)
        if members is None:
            return "its group's members could not be read"
        unread = []
        for uid in sorted(members):
            groups = _groups(uid)
            if groups is None:                            # said for that account; the walk goes on (P44)
                unread.append(_name(uid))
                continue
            if _passes(uid, groups, st, bits) and all(_passes(uid, groups, a, 1) for a in above):
                return f"account {_name(uid)} of its group can reach and write it"
        if unread:
            return f"the groups of account {', '.join(unread[:3])} in its group could not be read"
    return None


def _name(uid):
    import pwd
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def owned_by_another(path):
    """P42 (the family's rule 28): the folders from `path` up to the root that an account other than this one and
    root owns, and that account can reach (every folder above lets it pass): (folder, mode, owner's name)."""
    try:
        chain, p = [], os.path.abspath(path)
        while True:
            chain.append((p, os.stat(p)))
            if os.path.dirname(p) == p:
                break
            p = os.path.dirname(p)
    except OSError:
        return []
    me, out = os.getuid(), []
    for i, (p, st) in enumerate(chain):
        if st.st_uid in (me, 0):
            continue
        groups = _groups(st.st_uid) or set()
        if all(_passes(st.st_uid, groups, a, 1) for _, a in chain[i + 1:]):
            out.append((p, st.st_mode & 0o777, _name(st.st_uid)))
    return out


def runs_from(home, settings_path):
    """P47 (the family's rule 28, WHAT RUNS INCLUDES WHAT DECIDES WHAT RUNS): outside Pit Board's own home, every
    folder and file whose content decides what Pit Board runs: the settings file (its status line entry) and its
    folder; the folder above a home that is not the default; every installed version folder in Claude Code's plugin
    cache with everything in it (the hooks run from there); and every folder from the person's home folder down to
    each. ([paths], the registry's read when it could not be read, else None)."""
    top = os.path.expanduser("~")
    home = os.path.abspath(home)
    targets = [os.path.abspath(settings_path), os.path.dirname(os.path.abspath(settings_path))]
    if home != os.path.join(top, ".pitboard"):
        targets.append(os.path.dirname(home))
    installs = launch._registry(os.path.dirname(os.path.abspath(settings_path)))
    for path, _ in installs or []:
        if os.path.isdir(path) and not os.path.islink(path):
            targets.append(os.path.abspath(path))
            for d, dirs, files in os.walk(path):
                targets += [os.path.join(d, n) for n in sorted(dirs) + sorted(files)]
    out = []
    for t in targets:
        if t == home or t.startswith(home + os.sep):
            continue                                      # Pit Board's own: closed by own_open
        chain, p = [], t
        while p.startswith(top + os.sep) and p != top:
            chain.append(p)
            p = os.path.dirname(p)
        chain.append(top) if t.startswith(top + os.sep) or t == top else None
        out += [c for c in reversed(chain) if c not in out]
        if t not in out:
            out.append(t)
    return out, ("Claude Code's plugin registry" if installs is None else None)


def way_open(home, settings_path):
    """P41: folders on the way that are not Pit Board's and that it cannot know it made: the folder above the settings
    file, and the folder above a home that is not the default one. Never changed; named only when another account can
    really reach and write it, with the one command; and (P42) any folder on their way up that another account (not
    root) owns and can reach, with no command: only an administrator can hand it back. (path, mode, why, command)."""
    way, unread = runs_from(home, settings_path)
    out, seen = [], set()
    if unread:
        out.append((os.path.join(os.path.dirname(os.path.abspath(settings_path)), "plugins"), 0, f"{unread} could not "
                    "be read, so the installed copy's folders were not walked", None))   # mode 0: nothing read
    for w in way:
        for p, m, owner in owned_by_another(w):
            if p not in seen:
                seen.add(p)
                out.append((p, m, f"owned by account {owner}; only an administrator can hand it back", None))
        why = None if w in seen else who_can_write(w)
        if why:
            seen.add(w)
            st = os.lstat(w)
            if st.st_uid != os.getuid():                  # root's (rule 28): the person cannot run chmod on it
                who = "root" if st.st_uid == 0 else f"account {_name(st.st_uid)}"
                out.append((w, st.st_mode & 0o777, f"owned by {who}, and {why}; only an administrator can close it", None))
            else:
                out.append((w, st.st_mode & 0o777, why, f"chmod go-w {shlex.quote(w)}"))
    return out


READ_FROM = "read from its owner, group and mode; access lists (ACLs) are not read"


def closing_items(home, settings_path):
    """P41 (the family's rule 28, a file is only as closed as the folders above it)."""
    items = []
    own = own_open(home)
    if own:
        rel = [f"{os.path.relpath(p, home) if p != home else '.'} ({_open_mode(p):o})" for p in own]
        items.append(Item("Pit Board's own, open to other accounts", home,
                          "\n".join(["would close: group and other write taken off"] + rel), close=own))
    for w, m, why, fix in way_open(home, settings_path):
        kind = "a file that decides what runs" if os.path.isfile(w) else "a folder on the way"
        items.append(Item(f"{kind}, not Pit Board's", w,
                          "\n".join([(f"{m:o}: " if m else "") + f"{why}; setup does not change it", READ_FROM]
                                    + ([f"to close it: {fix}"] if fix else [])), name_only=True))
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


def note(home, settings=None, folder=None, backup=None, made=None, made_dirs=None, made_home=False):
    """G18.3: the record of what setup did, `setup-record.json` in the home, for `pitboard uninstall`.
    settings = (path, bytes before or None, mode before or None, bytes after): the earliest `before` stays while the
    file is still what Pit Board last wrote. backup = the name of the backup setup made of it: the census counts only
    the backups listed here, because other tools name theirs the same way (P29). made_home: setup made the home itself
    (P48); once said, it stays. A record that cannot be read is never written over."""
    path = os.path.join(home, leave.SETUP_RECORD)
    try:
        rec = leave.read_object(path) or {}
    except leave.Unread:
        return
    rec["version"] = __version__
    if made_home:
        rec["made_home"] = True
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
        dirs = [x for x in (old or {}).get("made_dirs") or [] if isinstance(x, str)]
        if made_dirs or dirs:                                 # P46: folders setup made for this file, deepest first
            entry["made_dirs"] = dirs + [x for x in made_dirs or [] if x not in dirs]
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
        made_dirs, d = [], os.path.dirname(os.path.abspath(it.path))
        while not os.path.lexists(d) and os.path.dirname(d) != d:   # P46: the folders this makes, deepest first
            made_dirs.append(d)
            d = os.path.dirname(d)
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
            note(home, settings=(it.path, before, before_mode, content), backup=bak, made_dirs=made_dirs)
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
