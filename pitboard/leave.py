"""pitboard uninstall (plan G18.3, P17): take Pit Board, and everything it made, off this computer.

One way of leaving for the plugin and for the stable copy: this file uses the standard library only and imports
nothing else of Pit Board, so `$PITBOARD_HOME/pitboard/leave.py` runs it to the end with no plugin folder anywhere
(after Claude Code's own `plugin uninstall`, and after Claude Code removed the orphaned folder too). The launcher
runs it for `uninstall`; `cli.main()` does too, for a launcher copy from before 0.1.3.

Plan first; `--apply` does it. Every read a step hangs on answers yes, no or could not be read; on the third
nothing is deleted, emptied or reported gone (exit 11). What is the person's stays and is counted: their asks
(lanes/, lanes.json) and the record of what Pit Board did (logs/, setup-record.json, setup's backups of their
settings files). `--delete-asks-and-log` deletes the asks and the log, only at a terminal, when the person types the
count. The last thing printed is a census; a second run is safe.
"""
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
import time

try:
    import fcntl
except ImportError:            # not POSIX: no lane locks to wait for
    fcntl = None

PLUGIN = "windstorm-pit-board"
FOLDER_RECORD = "pitboard-folder.json"
SETUP_RECORD = "setup-record.json"
WRAPPER = "statusline.sh"
MARK = "# pitboard-original-command: "
CLAUDE_LIMIT_SECONDS = 120     # as G21.3
LOCK_WAIT_SECONDS = 3          # as G2.3 for commands
TOOL = ("bin", "pitboard", WRAPPER, "config.json", "update", "state")   # what Pit Board made in a home, to go
PERSON = ("lanes", "lanes.json", "logs", SETUP_RECORD)                   # the person's, to keep and count
INCOMPLETE, BUSY, USAGE = 11, 7, 2
# P40 (the family's rule 23): what Pit Board makes in its home, by name, one level into its own folders. A home that
# holds anything else, or is the person's home folder, is not Pit Board's alone: setup refuses it and uninstall
# removes nothing from it.
_S = r"(\.prev|\.bak-[0-9-]+|\.tmp|\.[0-9]+\.tmp)?"
OWN_NAMES = {
    "": re.compile(r"(bin|pitboard|state|update|lanes|logs|statusline\.sh|config\.json|lanes\.json|lanes\.json\.lock|"
                   r"setup-record\.json)" + _S + r"|\.refresh-.+"),
    "bin": re.compile(r"pitboard" + _S),
    "pitboard": re.compile(r"(launch\.py|leave\.py|copied-from|__pycache__)" + _S),
    "state": re.compile(r"[a-z0-9][a-z0-9-]*\.(json|activity|wake|page-told|reminded)" + _S + r"|permission-open"),
    "update": re.compile(r"(last-check\.json|good-versions|bad-versions|pin|minute|last-seen-version|generation-shown)"
                         + _S),
    "lanes": re.compile(r"[a-z0-9][a-z0-9-]*\.(jsonl|lock)" + _S),
    "logs": re.compile(r"pitboard\.log(\.[0-9]+)?" + _S),
    "pitboard/__pycache__": re.compile(r"[A-Za-z0-9_.-]+\.pyc"),
    "update/generation-shown": re.compile(r"[A-Za-z0-9_.-]+"),
}


def is_home_folder(home):
    try:
        return os.path.realpath(home) == os.path.realpath(_home_dir())
    except OSError:
        return True                                           # cannot tell: treat it as the person's


def foreign(home):
    """P40: the paths in `home`, relative to it, that Pit Board does not make, read one level into its own folders.
    A folder that cannot be listed is named as could not be read: never taken for empty."""
    out = []

    def walk(rel):
        here = os.path.join(home, rel) if rel else home
        try:
            names = sorted(os.listdir(here))
        except FileNotFoundError:
            return
        except OSError as e:
            out.append(f"{rel or '.'} (could not be read: {type(e).__name__})")
            return
        pat = OWN_NAMES.get(rel)
        for n in names:
            sub = f"{rel}/{n}" if rel else n
            full = os.path.join(here, n)
            if pat is None or not pat.fullmatch(n) or os.path.islink(full):
                out.append(sub)
            elif os.path.isdir(full):
                if sub in OWN_NAMES:
                    walk(sub)
                elif not sub.startswith(".refresh-"):
                    out.append(sub + "/")
    walk("")
    return out


MARKS = {"bin/pitboard": "# Windstorm Pit Board", "pitboard/launch.py": '"""Pit Board launcher',
         "pitboard/leave.py": '"""pitboard uninstall', "statusline.sh": "# Written by pitboard setup"}
_SUFFIX = re.compile(_S + "$")


def marked(home, rel):
    """P40: the file carries Pit Board's own first lines (its copies .prev, .bak- and .tmp too). Read, never assumed."""
    want = MARKS.get(_SUFFIX.sub("", rel, count=1))
    if not want:
        return False
    try:
        with open(os.path.join(home, rel), "rb") as f:
            return want.encode() in f.read(400)
    except OSError:
        return False


def recorded(home, rel):
    """P40: setup's record lists this file as one setup made (from 0.1.3)."""
    try:
        rec = read_object(os.path.join(home, SETUP_RECORD)) or {}
    except Unread:
        return False
    return rel in [m for m in rec.get("made") or [] if isinstance(m, str)]


def foreign_text(found, most=5):
    more = f" and {len(found) - most} more" if len(found) > most else ""
    return ", ".join(found[:most]) + more


# ------------------------------------------------------------------ three answers

class Unread(Exception):
    """A read a step hangs on could not be made: not "absent" (family rule 6)."""


def read_bytes(path):
    """The file's bytes; None when it is missing; Unread when it is there and cannot be read."""
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise Unread(f"{path} could not be read ({type(e).__name__})")


def read_object(path):
    """A JSON object; None when the file is missing; Unread when it cannot be read or is not an object."""
    raw = read_bytes(path)
    if raw is None:
        return None
    try:
        d = json.loads(raw.decode("utf-8")) if raw.strip() else {}
    except ValueError as e:
        raise Unread(f"{path} could not be read ({type(e).__name__})")
    if not isinstance(d, dict):
        raise Unread(f"{path} is not a JSON object")
    return d


def write_new(path, data, mode=0o600):
    """P41 (the family's rule 28): a file is OPENED NEW at its final mode (O_EXCL, never a file that was already there:
    a leftover is removed first), so it is never written at a wider mode and narrowed after. The mode is set on the open
    file before any byte goes in (the umask may have taken bits the mode keeps, as a backup's 664). A file already at
    `path` is never removed or written here: the open fails (FileExistsError)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        if os.fstat(fd).st_mode & 0o777 != mode:
            os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as f:
            fd = None
            f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def write_atomic(path, data, mode=0o600):
    """Write whole or not at all: a new temporary file of this process beside it (write_new), then a rename."""
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        os.unlink(tmp)                                   # one this process id left before: never reused
    except FileNotFoundError:
        pass
    write_new(tmp, data, mode)
    os.replace(tmp, path)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------ Claude Code's plugin command

PROGRESS = ("SSH not configured, cloning via HTTPS:", "HTTPS clone failed, retrying with SSH:")   # printed last
NO_KEY = ("Host key verification failed", "Permission denied (publickey)")
NOT_SET_UP = "this account is not set up for GitHub over SSH (GitHub accepted no key from it)"
ERROR_LINES = 12
WRAP = 100   # G6.8's width: these lines are wrapped to it, so the CLI never has to cut one


def error_text(stdout, stderr):
    """G18.1 step 6 (P9): Claude Code's error from its first error line (the first that starts with ✘, or else the
    first line of its error output) to the end, at most 12 lines, without its progress lines; first, in plain words,
    when the clone failed over SSH because GitHub accepted no key, with what to do. Every line is wrapped to G6.8's
    100 columns (a continued line starts with two spaces), so nothing is cut."""
    out, err = (stdout or "").splitlines(), (stderr or "").splitlines()
    lines = [ln.rstrip() for ln in out + err]
    start = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith("✘")), None)
    if start is None:
        start = len(out) if any(ln.strip() for ln in err) else 0
    body = [ln for ln in lines[start:] if ln.strip() and not ln.startswith(PROGRESS)][:ERROR_LINES]
    whole = "\n".join(lines)
    head = []
    if any(k in whole for k in NO_KEY):
        if "HTTPS clone failed, retrying with SSH" in whole:
            head = [f"Claude Code could not clone the plugin from GitHub over HTTPS, and the retry over SSH failed: "
                    f"{NOT_SET_UP}.", "Check that this machine reaches github.com over HTTPS, or add a GitHub key to "
                    "this account, then run the same command again."]
        else:
            head = [f"Claude Code could not clone the plugin from GitHub over SSH; {NOT_SET_UP}.",
                    "Update Claude Code (2.1.330 clones over HTTPS when SSH is not set up), or add a GitHub key to "
                    "this account, then run the same command again."]
    return "\n".join(w for ln in head + body for w in textwrap.wrap(ln, WRAP, subsequent_indent="  ",
                                                                     break_on_hyphens=False) or [""])


def claude(args, cwd, run=None):
    """Run `claude ...` in cwd: (ok, Claude Code's error when it failed, whether `claude` was missing)."""
    run = run or subprocess.run
    try:
        r = run(["claude"] + args, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                timeout=CLAUDE_LIMIT_SECONDS)
    except FileNotFoundError:
        return False, "`claude` is not on the PATH", True
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e), False
    return r.returncode == 0, ("" if r.returncode == 0 else error_text(r.stdout, r.stderr)), False


# ------------------------------------------------------------------ what Claude Code's own uninstall did (P30)

def _print(path):
    """(size, mtime_ns, sha256) of a file, "missing", or "unreadable": read, never assumed."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        st = os.stat(path)
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "unreadable"
    return (st.st_size, st.st_mtime_ns, hashlib.sha256(data).hexdigest())


def claude_files():
    """The files of Claude Code's own that its `plugin uninstall` was seen to change (rule 23 round, P30)."""
    return [os.path.join(claude_dir(), "plugins", "installed_plugins.json"), os.path.join(_home_dir(), ".claude.json")]


def claude_left(census, names, before):
    """P30: after Claude Code's own uninstall, name what it changed and what it kept, as read now. `names` are the
    plugins it uninstalled; `before` the prints of claude_files() taken before the first call."""
    changed = [_short(p) for p in claude_files() if before.get(p) != _print(p)]
    if changed:
        census.kept("Claude Code's own files: " + ", ".join(changed),
                    "changed by Claude Code's own uninstall, which Pit Board ran; they are Claude Code's")
    cats = []
    for name in names:
        plugin, _, cat = name.partition("@")
        if cat and cat not in cats:
            cats.append(cat)
        top = os.path.join(claude_dir(), "plugins", "cache", cat, plugin)
        try:
            vers = sorted(v for v in os.listdir(top) if os.path.isdir(os.path.join(top, v)))
        except FileNotFoundError:
            vers = []
        except OSError as e:
            census.kept(_short(top), f"could not be read ({type(e).__name__}), so Pit Board cannot say what Claude "
                                     "Code kept there")
            continue
        for v in vers:
            d = os.path.join(top, v)
            marked = os.path.exists(os.path.join(d, ".orphaned_at"))
            census.kept(_short(d), "Pit Board's code, a version folder Claude Code keeps in its plugin cache after its "
                        "own uninstall" + (" (it marked it .orphaned_at)" if marked else "")
                        + "; Claude Code's to clean up, so Pit Board leaves it")
    known = os.path.join(claude_dir(), "plugins", "known_marketplaces.json")
    for cat in cats:
        try:
            with open(known, encoding="utf-8") as f:
                listed = cat in (json.load(f) or {})
        except FileNotFoundError:
            listed = False
        except (OSError, ValueError, TypeError) as e:
            census.kept(f"the plugin catalog {cat}", f"{_short(known)} could not be read ({type(e).__name__}), "
                        "so Pit Board cannot say whether Claude Code still lists it")
            continue
        if listed:
            census.kept(f"the plugin catalog {cat} in Claude Code's list",
                        "other plugins install and update from it; removing it with `claude plugin marketplace remove "
                        f"{cat}` also uninstalls every plugin installed from that catalog, so Pit Board leaves it")


# ------------------------------------------------------------------ the census

class Census:
    def __init__(self, apply=True):
        self.rows, self.code, self.apply = [], 0, apply

    def gone(self, what, how=""):
        self.rows.append(("gone" if self.apply else "would go", what, how))

    def kept(self, what, why, code=0):
        self.rows.append(("kept", what, why))
        self.code = max(self.code, code)

    def lines(self):
        return [f"  {state}: {what}" + (f" ({why})" if why else "") for state, what, why in self.rows]


def _home_dir():
    return os.path.expanduser("~")


def _short(path):
    h = _home_dir()
    return "~" + path[len(h):] if path == h or path.startswith(h + os.sep) else path


def _n(count, word):
    return f"{count} {word}" + ("" if count == 1 else "s")


def _shell(path):
    """The path as a person types it in a shell: ~/... when it is under the home folder and needs no quoting."""
    short = _short(path)
    return short if short.startswith("~/") and shlex.quote(short[2:]) == short[2:] else shlex.quote(path)


def default_home():
    return os.path.join(_home_dir(), ".pitboard")


def claude_dir():
    return os.path.join(_home_dir(), ".claude")


# ------------------------------------------------------------------ one folder (G18.1 folder mode)

class NoRecord(Exception):
    """The folder has no record: setup --folder did not set up here."""


def _drop(d, home, plugin, strip_env=True):
    """d without Pit Board's entries: the home's wrapper as statusLine, the plugin key, the home in env."""
    d = dict(d)
    if (d.get("statusLine") or {}).get("command") == os.path.join(home, WRAPPER):
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


def folder_undo(folder, run=None, envhome=None, census=None, apply=True, went=None):
    """Uninstall the plugin from one folder and put its settings back (G18.1 folder mode, now G18.3's).
    Returns (lines, home). Raises NoRecord when the folder has no record, Unread when the record cannot be read."""
    census = census if census is not None else Census()
    folder = os.path.realpath(folder)
    cd = os.path.join(folder, ".claude")
    ls, rec = os.path.join(cd, "settings.local.json"), os.path.join(cd, FOLDER_RECORD)
    r = read_object(rec)
    if r is None:
        raise NoRecord(f"no record at {rec}: setup --folder did not set up here")
    plugin, before = r.get("plugin") or f"{PLUGIN}@thewindstorm", r.get("settings_local_before")
    home = r.get("home") or envhome or os.environ.get("PITBOARD_HOME") or default_home()
    if not apply:
        census.gone(f"Pit Board in {folder}", f"claude plugin uninstall {plugin} --scope local there, then its "
                    "settings back")
        return [], home
    out = []
    ok, tail, missing = claude(["plugin", "uninstall", plugin, "--scope", "local"], folder, run)
    out.append(f"plugin {plugin}: " + ("removed from this folder" if ok else f"uninstall said:\n{tail}"))
    if ok:
        census.gone(f"plugin {plugin} in {folder}")
        if went is not None:
            went.append(plugin)
    else:
        census.kept(f"plugin {plugin} in {folder}", f"run yourself: cd {_shell(folder)} && claude plugin uninstall "
                    f"{plugin} --scope local" if missing else "Claude Code's uninstall failed; its error is above",
                    INCOMPLETE)
    try:
        now = read_object(ls) or {}
    except Unread as e:            # never write a settings file that could not be read
        census.kept(f"{ls}", f"{e}; nothing in it was changed", INCOMPLETE)
        out.append(f"{ls}: {e}; nothing in it was changed, and the record stays for the next run")
        return out, home
    old = json.loads(before) if before and before.strip() else {}
    keep_env = (old.get("env") or {}).get("PITBOARD_HOME") == home   # the person's own, set before setup
    mine = _drop(now, home, plugin, not keep_env)
    if mine == _drop(old, home, plugin, not keep_env):
        if before is None:
            if os.path.exists(ls):
                os.remove(ls)
            how = "removed (there was none before)"
        else:
            write_atomic(ls, before)
            how = "put back byte for byte"
    else:
        write_atomic(ls, json.dumps(mine, indent=2) + "\n")
        how = "Pit Board's entries removed; other changes made since setup are kept"
    os.remove(rec)
    if not r.get("claude_dir_existed", True) and os.path.isdir(cd) and not os.listdir(cd):
        os.rmdir(cd)
    census.gone(f"{ls}: Pit Board's settings", how)
    out.append(f"{ls}: {how}")
    out += [f"Pit Board is off in {folder}.", f"Its asks stay in {home}.",
            "Restart or resume the session there to drop the hooks."]
    return out, home


# ------------------------------------------------------------------ the person's settings file

def _original_from_wrapper(wpath):
    """The person's own status line command, as the wrapper recorded it: str, "" (none), or Unread."""
    raw = read_bytes(wpath)
    if raw is None:
        return None
    for line in raw.decode("utf-8", "replace").splitlines():
        if line.startswith(MARK):
            try:
                v = json.loads(line[len(MARK):])
            except ValueError:
                raise Unread(f"{wpath}'s recorded command could not be read")
            return v if isinstance(v, str) else ""
    raise Unread(f"{wpath} has no recorded command")


def settings_back(path, home, entry, census, apply):
    """G18.3 point 3: put one settings file back. Returns True when nothing of Pit Board's is left in it."""
    wpath = os.path.join(home, WRAPPER)
    try:
        raw = read_bytes(path)
        if raw is None:
            return True
        if entry and entry.get("after_sha256") == sha256(raw):
            before = entry.get("before")
            if apply:
                if before is None:
                    os.remove(path)
                else:
                    write_atomic(path, before, entry.get("before_mode") or os.stat(path).st_mode & 0o777)
            census.gone(f"status line setting in {_short(path)}",
                        "put back byte for byte" if before is not None else "file removed: there was none before")
            return True
        d = read_object(path)
        sl = d.get("statusLine")
        if not (isinstance(sl, dict) and sl.get("command") == wpath):
            return True
        old = None
        if entry and entry.get("before"):
            try:
                old = json.loads(entry["before"]).get("statusLine")
            except (ValueError, AttributeError):
                old = None
        if old is None:
            orig = _original_from_wrapper(wpath)
            old = dict(sl, command=orig) if orig else None
        new = dict(d)
        if old is None:
            new.pop("statusLine", None)
        else:
            new["statusLine"] = old
        if apply:
            write_atomic(path, json.dumps(new, indent=2, ensure_ascii=False) + "\n", os.stat(path).st_mode & 0o777)
        census.gone(f"status line setting in {_short(path)}", "Pit Board's entry taken out; the rest kept"
                    + ("; your own status line is back" if old else ""))
        return True
    except Unread as e:
        census.kept(f"status line setting in {_short(path)}", f"{e}; the file was not touched", INCOMPLETE)
        return False
    except OSError as e:
        census.kept(f"status line setting in {_short(path)}", f"could not be written ({type(e).__name__})", INCOMPLETE)
        return False


# ------------------------------------------------------------------ a home

def count_asks(home):
    """(asks, open, lane logs) in the home's lanes/; Unread when a lane log cannot be read."""
    lanes = os.path.join(home, "lanes")
    try:
        names = sorted(n for n in os.listdir(lanes) if n.endswith(".jsonl"))
    except FileNotFoundError:
        return 0, 0, 0
    except OSError as e:
        raise Unread(f"{lanes} could not be read ({type(e).__name__})")
    status = {}
    for n in names:
        raw = read_bytes(os.path.join(lanes, n)) or b""
        for line in raw.decode("utf-8", "replace").splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            t, uid = (ev.get("type"), ev.get("uid")) if isinstance(ev, dict) else (None, None)
            if uid and t in ("asked", "reopened"):
                status[uid] = "open"
            elif uid and t in ("answered", "done", "withdrawn"):
                status[uid] = "closed"
    return len(status), sum(1 for s in status.values() if s == "open"), len(names)


def lock_holder(home):
    """The lane whose lock a writer holds now, after waiting as other commands do; None when none is held."""
    if fcntl is None:
        return None
    locks = [os.path.join(home, "lanes.json.lock")]
    try:
        locks += [os.path.join(home, "lanes", n) for n in os.listdir(os.path.join(home, "lanes")) if n.endswith(".lock")]
    except OSError:
        pass
    end = time.monotonic() + LOCK_WAIT_SECONDS
    for path in locks:
        while True:
            try:
                fd = os.open(path, os.O_RDWR)
            except OSError:
                break
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fd, fcntl.LOCK_UN)
                break
            except OSError:
                if time.monotonic() >= end:
                    return os.path.basename(path)[:-len(".lock")]
                time.sleep(0.1)
            finally:
                os.close(fd)
    return None


def _is_tool(name):
    base = name.split(".bak-")[0]
    return (base in TOOL or name.startswith(".refresh-") or name.endswith(".tmp")
            or name in ("lanes.json.lock", "lanes.json.tmp"))


def _remove(path, census, apply, label=None):
    """One file, or one folder only when it is empty (rule 23: a folder goes only when empty)."""
    try:
        if apply:
            os.rmdir(path) if os.path.isdir(path) and not os.path.islink(path) else os.remove(path)
        if label:
            census.gone(label)
        return True
    except OSError as e:
        census.kept(_short(path), f"could not be removed ({type(e).__name__})", INCOMPLETE)
        return False


def _files_in(home, rel):
    """Every path under home/rel, deepest first (files before their folders), relative to home."""
    out = []
    for d, dirs, files in os.walk(os.path.join(home, rel), topdown=False):
        r = os.path.relpath(d, home)
        out += [os.path.join(r, f) for f in sorted(files)] + [os.path.join(r, x) for x in sorted(dirs)]
    return out


def home_off(home, census, apply, blocked=""):
    """G18.3 point 5 and P40 (rules 23 and 8). What carries Pit Board's mark, or setup's record lists, goes wherever it
    is. Pit Board's other files go only from folders that hold nothing but Pit Board's own names; a folder goes only
    when it is empty. Anything else stays and is named, with whose it is. A home that is not Pit Board's alone never
    stops the leave: everything outside it already came off. Returns the kept line, if any."""
    try:
        names = sorted(os.listdir(home))
    except FileNotFoundError:
        return None
    except OSError as e:
        census.kept(_short(home), f"could not be read ({type(e).__name__})", INCOMPLETE)
        return None
    if blocked:
        census.kept(f"Pit Board's files in {_short(home)}", f"{blocked}; they stay so that "
                    f"{_short(os.path.join(home, 'bin', 'pitboard'))} uninstall can run again", INCOMPLETE)
        return None
    try:                                                      # every read first: nothing goes on an unread one
        asks, open_, logs = count_asks(home)
    except Unread as e:
        census.kept(f"Pit Board's files and your asks in {_short(home)}", f"{e}; nothing in this home was changed",
                    INCOMPLETE)
        return None
    if apply:
        held = lock_holder(home)
        if held:
            census.kept(f"Pit Board's files in {_short(home)}", f"a session is writing to lane {held} now; "
                        "run uninstall again in a moment", BUSY)
            return None
    yours_folder = is_home_folder(home)
    found = foreign(home)
    top_foreign = [f for f in found if "/" not in f.rstrip("/")]
    shared = {f.split("/", 1)[0] for f in found if "/" in f.rstrip("/")}   # Pit Board's folders holding another's
    alone = not yours_folder and not top_foreign              # the home itself is Pit Board's alone
    why_top = "your home folder" if yours_folder else ", ".join(top_foreign[:3]) + (" and more" if len(top_foreign) > 3 else "")
    left = False
    for name in names:
        path = os.path.join(home, name)
        if name in top_foreign:
            census.kept(_short(path), "not made by Pit Board; yours")
            left = True
            continue
        if os.path.isdir(path) and not os.path.islink(path):
            if name in ("lanes", "logs"):                     # the person's asks and log: kept and counted below
                if name == "logs" and not os.listdir(path) and not yours_folder:
                    _remove(path, census, apply, _short(path))  # P43: an empty logs/ is an empty folder of Pit Board's
                    continue
                if name == "lanes" and not yours_folder and name not in shared:
                    for rel in _files_in(home, name):
                        if rel.endswith(".lock"):
                            _remove(os.path.join(home, rel), census, apply)
                continue
            mine_only = not yours_folder and name not in shared     # this folder holds only Pit Board's names
            gone_all = True
            for rel in _files_in(home, name):
                full = os.path.join(home, rel)
                if os.path.isdir(full):
                    if mine_only or not os.listdir(full) and not yours_folder:
                        gone_all = _remove(full, census, apply) and gone_all
                    else:
                        gone_all = False
                elif marked(home, rel) or mine_only:
                    gone_all = _remove(full, census, apply) and gone_all
                else:
                    gone_all = False
            if mine_only or (not yours_folder and gone_all):
                if _remove(path, census, apply, _short(path)) is False:
                    left = True
            else:
                theirs = [f for f in found if f.startswith(name + "/")]
                census.kept(_short(path), "Pit Board's, left because " + (
                    f"{', '.join(theirs[:3])} in it is not" if theirs else "it is in your home folder")
                    + "; yours to delete after looking inside")
                left = True
            continue
        if name in PERSON:
            continue
        if marked(home, name) or (name == "config.json" and recorded(home, name)) or alone:
            _remove(path, census, apply, _short(path))
        else:
            census.kept(_short(path), "Pit Board's, left because " + (
                "it is in your home folder" if yours_folder else f"{why_top} beside it is not")
                + "; yours to delete after looking at it")
            left = True
    kept = [n for n in PERSON if os.path.exists(os.path.join(home, n))
            and not (n == "logs" and os.path.isdir(os.path.join(home, n)) and not os.listdir(os.path.join(home, n)))]
    if not kept and not left:
        if apply and not yours_folder:
            try:
                os.rmdir(home)
            except OSError:
                pass
        return None
    if kept:                                                  # P43: only what is there is named
        parts = ([f"{_n(asks, 'ask')} ({open_} open) in {_n(logs, 'lane log')}"]
                 if "lanes" in kept or "lanes.json" in kept else [])
        parts += ["the log of what Pit Board did"] if "logs" in kept else []
        parts += [f"setup's record ({SETUP_RECORD})"] if SETUP_RECORD in kept else []
        census.kept(f"{', '.join(parts[:-1]) + ', and ' + parts[-1] if len(parts) > 1 else parts[0]} "
                    f"in {_short(home)}", "yours")                # one row with the count; the line below says how
    if left:                                                  # P40: no command for a folder that is not Pit Board's alone
        return (f"Pit Board is off this computer. What it left in {_short(home)}, and why, is named above; it is "
                "yours, to keep or delete after you look at it.")
    copy = os.path.join(home, "bin", "pitboard")             # rule 7: only a line run as printed, this computer's way
    return ("They are yours. When you are sure, you can delete them yourself, at your own terminal: "  # the person's act
            + (f"{_shell(copy)} uninstall --apply --delete-asks-and-log" if os.path.isfile(copy) else f"rm -r {_shell(home)}"))


def ask_count(homes, stdin, stdout):
    """G18.3 point 6, first: the person types the count before anything changes. {home: count} when they typed it,
    {} when there is nothing to delete, None when they did not (then nothing at all changes)."""
    found = {}
    for h in homes:
        if os.path.isdir(h) and any(os.path.exists(os.path.join(h, n)) for n in PERSON) and not foreign(h) and not is_home_folder(h):
            found[h] = count_asks(h)                          # Unread goes up: nothing changes
    if not found:
        return {}
    total = sum(c[0] for c in found.values())
    for h, (asks, open_, logs) in found.items():
        stdout.write(f"This deletes {_n(asks, 'ask')} ({open_} open) in {_n(logs, 'lane log')} and the log of what "
                     f"Pit Board did, at {_short(h)}, after it takes Pit Board off.\n")
    stdout.write(f"Type {total} to do both, or anything else to change nothing: ")
    stdout.flush()
    if stdin.readline().strip() != str(total):
        return None
    return {h: c[0] for h, c in found.items()}


def delete_kept(home, expected, census):
    """G18.3 point 6: delete the asks and the log the person counted, unless the count changed since."""
    mine = f"your asks and the log of what Pit Board did, in {_short(home)}"
    counted = f" in {_short(home)}"                            # home_off's one counted row (P43: its words vary)
    census.rows = [r for r in census.rows if not (r[0] == "kept" and r[1].endswith(counted) and r[2] == "yours")]
    try:
        now = count_asks(home)[0]
    except Unread as e:
        census.kept(mine, f"{e}; nothing deleted", INCOMPLETE)
        return
    if now != expected:
        census.kept(mine, f"there are {now} asks now, not the {expected} you typed; nothing deleted")
        return
    found = ["your home folder"] if is_home_folder(home) else foreign(home)
    if found:                                                 # P40: checked again at the moment of deleting
        census.kept(mine, f"{foreign_text(found)} is there too, and is not Pit Board's; nothing deleted")
        return
    for n in PERSON:
        p = os.path.join(home, n)
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.exists(p):
            os.remove(p)
    try:
        os.rmdir(home)
    except OSError:
        pass
    census.gone(mine, "you typed the count")


# ------------------------------------------------------------------ the whole computer

def registry(cdir):
    """Pit Board's rows in Claude Code's plugin registry: [(name, scope, projectPath)]; Unread when unreadable."""
    path = os.path.join(cdir, "plugins", "installed_plugins.json")
    d = read_object(path)
    if d is None:
        return []
    plugins = d.get("plugins", {})
    if not isinstance(plugins, dict):
        raise Unread(f"{path} has no object of plugins")
    return [(name, str(e.get("scope") or ""), str(e.get("projectPath") or ""))
            for name, entries in plugins.items() if name.split("@", 1)[0] == PLUGIN and isinstance(entries, list)
            for e in entries if isinstance(e, dict)]


def _backups(path):
    d, base = os.path.split(path)
    try:
        return sorted(n for n in os.listdir(d) if n.startswith(base + ".bak-"))
    except OSError:
        return []


def _homes(extra=()):
    out = []
    for h in [default_home(), os.environ.get("PITBOARD_HOME")] + list(extra):
        if h and os.path.realpath(h) not in [os.path.realpath(x) for x in out]:
            out.append(h)
    return out


def uninstall(apply=True, folder=None, run=None, census=None):
    """G18.3. Returns (lines to print before the census, kept lines, census, homes)."""
    census = census or Census(apply)
    out, kept_lines = [], []
    before, went = {p: _print(p) for p in claude_files()}, []       # P30: what Claude Code's own uninstall does
    if folder:
        try:
            lines, _ = folder_undo(folder, run=run, census=census, apply=apply, went=went)
            out += lines
        except NoRecord as e:
            census.kept(folder, f"{e}; nothing changed", INCOMPLETE)
        except Unread as e:
            census.kept(folder, f"{e}; nothing changed", INCOMPLETE)
        if went:
            claude_left(census, went, before)
        return out, kept_lines, census, []
    try:
        rows = registry(claude_dir())
    except Unread as e:
        rows = None
        census.kept("Pit Board's installs in Claude Code", f"{e}; no plugin install was changed", INCOMPLETE)
    homes = _homes()
    records = {}
    for h in list(homes):
        try:
            records[h] = read_object(os.path.join(h, SETUP_RECORD)) or {}
        except Unread as e:
            records[h] = None
            census.kept(f"the setup record in {_short(h)}", str(e), INCOMPLETE)
    folders = []
    for name, scope, project in rows or []:
        if scope == "local" and project:
            folders.append(project)
    for rec in records.values():
        for f in (rec or {}).get("folders", []):
            if isinstance(f, str):
                folders.append(f)
    seen_folders = set()
    for f in folders:                                         # the folders first: each holds its own settings
        real = os.path.realpath(f)
        if real in seen_folders or not os.path.exists(os.path.join(real, ".claude", FOLDER_RECORD)):
            continue
        seen_folders.add(real)
        try:
            lines, h = folder_undo(real, run=run, census=census, apply=apply, went=went)
            out += lines
            if h not in homes:
                homes.append(h)
        except (NoRecord, Unread) as e:
            census.kept(f"Pit Board in {real}", f"{e}; nothing there was changed", INCOMPLETE)
    settings_ok = {}
    for h in homes:                                           # then the person's settings files, so a running
        rec = records.get(h, {})                              # session's status line goes back to their own
        if rec is None:
            settings_ok[h] = False
            continue
        files = {e["path"]: e for e in rec.get("files", []) if isinstance(e, dict) and isinstance(e.get("path"), str)}
        files.setdefault(os.path.join(claude_dir(), "settings.json"), None)
        settings_ok[h] = all([settings_back(p, h, e, census, apply) for p, e in files.items()])
        for p, e in files.items():                           # only the backups setup's record lists (P29)
            listed = e.get("backups") if isinstance(e, dict) else None
            if isinstance(listed, list):
                d = os.path.dirname(p)
                baks = [b for b in listed if isinstance(b, str) and os.path.exists(os.path.join(d, b))]
                if baks:
                    census.kept(f"{_n(len(baks), 'backup')} setup made of {_short(p)}",
                                "yours: " + ", ".join(_short(os.path.join(d, b)) for b in baks))
            elif e is not None or not rec:                    # no list then; a file setup never changed has none
                others = _backups(p)
                if others:
                    census.kept(f"{_n(len(others), 'file')} named {_short(p)}.bak-*",
                                "setup kept no list of its backups then, so Pit Board cannot tell which are its own; "
                                "yours to keep or delete")
    for name, scope, project in rows or []:                   # then the plugin installs
        if scope == "local" and os.path.realpath(project) in seen_folders:
            continue
        where = project if scope in ("local", "project") and project else _home_dir()
        cmd = f"claude plugin uninstall {name} --scope {scope or 'user'}"
        if scope == "project":
            census.kept(f"plugin {name} in {project} (project scope)", "it lives in that repository's shared "
                        f"settings; to take it off there: cd {_shell(project)} && {cmd}")
            continue
        if not apply:
            census.gone(f"plugin {name} ({scope or 'user'} scope)", cmd)
            continue
        ok, tail, missing = claude(["plugin", "uninstall", name, "--scope", scope or "user"], where, run)
        if ok:
            user_settings = f"status line setting in {_short(os.path.join(claude_dir(), 'settings.json'))}"
            census.rows = [(st, w, y + "; then Claude Code's own uninstall changed its entries in that file")
                           if w == user_settings and st == "gone" and scope in ("", "user") else (st, w, y)
                           for st, w, y in census.rows]       # P17 ruling: byte for byte only where it is true
            census.gone(f"plugin {name} ({scope or 'user'} scope)")
            went.append(name)
        else:
            out.append(f"plugin {name} ({scope or 'user'} scope): uninstall said:\n{tail}")
            census.kept(f"plugin {name} ({scope or 'user'} scope)", f"run yourself: {cmd}", INCOMPLETE)
    if went:
        claude_left(census, went, before)
    unfinished = census.code != 0                             # a read failed or a step failed above
    for h in homes:                                           # last, each home: the running launcher copy goes last
        blocked = ("a status line setting still runs its wrapper; fix that file" if not settings_ok.get(h, True)
                   else "a step above was not finished" if unfinished else "")
        line = home_off(h, census, apply, blocked)
        if line:
            kept_lines.append(line)
    return out, kept_lines, census, homes


USAGE_LINE = "usage: pitboard uninstall [--folder DIR] [--apply] [--delete-asks-and-log] [--lane KEY] [--json]\n"


def _args(argv):
    """(apply, delete, folder, as_json) or None on bad usage. `--lane` is taken and not needed: uninstall is for
    the whole computer (G6.2: every command accepts it)."""
    apply = delete = as_json = False
    folder, i = None, 0
    while i < len(argv):
        a = argv[i]
        if a == "--apply":
            apply = True
        elif a == "--delete-asks-and-log":
            delete = True
        elif a == "--json":
            as_json = True
        elif a in ("--folder", "--lane") and i + 1 < len(argv):
            folder = argv[i + 1] if a == "--folder" else folder
            i += 1
        else:
            return None
        i += 1
    return apply, delete, folder, as_json


def main(argv=None, stdin=None, stdout=None, stderr=None, run=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    stdin, stdout, stderr = stdin or sys.stdin, stdout or sys.stdout, stderr or sys.stderr
    parsed = _args(argv)
    if parsed is None:
        stderr.write(USAGE_LINE)
        return USAGE
    apply, delete, folder, as_json = parsed
    if delete and not (apply and not folder and stdin.isatty() and stdout.isatty()):
        stderr.write("pitboard: --delete-asks-and-log runs only at your own terminal, with --apply: your asks are "
                     "yours to delete.\nNothing changed. `pitboard uninstall --apply` takes Pit Board off and keeps "
                     "them.\n")
        return USAGE
    counted = {}
    if delete:                                                # the count first: a wrong one changes nothing at all
        try:
            counted = ask_count(_homes(), stdin, stdout)
        except Unread as e:
            stderr.write(f"pitboard: {e}.\nNothing changed.\n")
            return INCOMPLETE
        if counted is None:
            stdout.write("\nYou did not type the count. Nothing changed.\n")
            return 0
        stdout.write("\n")
    out, kept_lines, census, homes = uninstall(apply=apply, folder=folder, run=run)
    if counted and census.code == 0:
        for h, expected in counted.items():
            delete_kept(h, expected, census)
            kept_lines = [ln for ln in kept_lines if _short(h) not in ln or os.path.isdir(h)]
    if delete:                                                # P40: say why a home's asks were not offered for deleting
        for h in homes:
            if h in (counted or {}) or not any(os.path.exists(os.path.join(h, n)) for n in PERSON):
                continue
            why = "it is your home folder" if is_home_folder(h) else (
                "it holds " + foreign_text(foreign(h)) + ", which Pit Board did not make" if foreign(h) else "")
            if why:
                census.kept(f"your asks and the log of what Pit Board did, in {_short(h)}",
                            f"you asked to delete them, but {why}; so nothing there was deleted. Yours to delete "
                            "after you look inside")
    text = list(out)
    if not any(state in ("gone", "would go") for state, _, _ in census.rows) and census.code == 0:
        text.append("nothing of Pit Board is here")
    if not apply:
        text.append("pitboard uninstall: the plan (nothing changes without --apply)")
    if census.rows:
        text += ["census:"] + census.lines()
    text += kept_lines
    if not apply:
        text.append("Nothing changed. Run again with --apply to do it.")
    if as_json:
        stdout.write(json.dumps({"ok": census.code == 0, "exit": census.code, "message": "\n".join(text), "ids": [],
                                 "asks": [], "data": {"applied": apply, "census": [
                                     {"state": st, "what": w, "why": y} for st, w, y in census.rows]}},
                                ensure_ascii=False) + "\n")
    else:
        stdout.write("".join(ln + "\n" for ln in text))
    return census.code


if __name__ == "__main__":
    sys.exit(main())
