"""Pit Board lane identity (plan G3): one key per lane across restarts, compactions and resumes.

Standard library only.
"""
import json
import os
import re

from . import contract, store

# G3.2 step 1: check C3 (docs/CONTRACTS.md) confirmed that SessionStart's session_title
# is only ever the /rename or --name name; a never-named session has none, headless or
# interactive. A --name session can lack the transcript record at its first SessionStart,
# so session_title comes first. Set False to fall back to the transcript alone.
SESSION_TITLE_IS_RENAME = True

TITLE_MARK = b'"custom-title"'
CHUNK = 1 << 20


class NoLane(Exception):
    """G3.7 step 4: the caller exits with code 3 and prints the message."""

    exit_code = 3


def map_path():
    return os.path.join(store.home(), "lanes.json")


def map_lock_path():
    return os.path.join(store.home(), "lanes.json.lock")


# ---------------------------------------------------------------- G3.1

def key_of(name, session_id):
    """G3.1: lower-case, every run of other characters becomes '-', trim '-', cut to 64.
    Empty → 'session-' + the first 8 characters of the session ID."""
    k = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:64].rstrip("-")
    if k:
        return k
    short = re.sub(r"[^a-z0-9]+", "", (session_id or "").lower())[:8] or "unknown"
    return "session-" + short


# ---------------------------------------------------------------- G3.2

def title_from_transcript(path):
    """G3.2 step 2: the newest custom-title record's customTitle, read from the end of the file."""
    if not path:
        return None
    try:
        f = open(path, "rb")
    except OSError:
        return None
    with f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        tail = b""
        while pos > 0:
            step = min(CHUNK, pos)
            pos -= step
            f.seek(pos)
            buf = f.read(step) + tail
            lines = buf.split(b"\n")
            tail = lines[0] if pos > 0 else b""  # a line cut by the chunk edge waits for the next chunk
            for raw in reversed(lines[1:] if pos > 0 else lines):
                if TITLE_MARK not in raw:
                    continue
                try:
                    rec = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(rec, dict) and rec.get("type") == "custom-title":
                    t = rec.get("customTitle")
                    if isinstance(t, str) and t.strip():
                        return t.strip()
    return None


def lane_name(session_title=None, transcript_path=None):
    """G3.2: the lane's name, or None (the key then falls back to session-<8>)."""
    if SESSION_TITLE_IS_RENAME and isinstance(session_title, str) and session_title.strip():
        return session_title.strip()
    return title_from_transcript(transcript_path)


# ---------------------------------------------------------------- G3.3 to G3.5

def read_map():
    m = store.read_json(map_path(), {})
    return m if isinstance(m, dict) else {}


def resolve(session_id, name=None, lock_timeout=store.LOCK_WAIT_COMMAND):
    """G3.4/G3.5: the lane key for a session. First sight computes and stores the key;
    after that the key never changes and a new name updates lane_name only.
    Returns the map row {"lane", "lane_name", "first_seen", "last_seen"}."""
    if not session_id:
        raise ValueError("session_id is required")
    store.ensure_home()
    now = contract.now_ts()
    with store.LaneLock(None, timeout=lock_timeout, path=map_lock_path()):
        m = read_map()
        row = m.get(session_id)
        if isinstance(row, dict) and contract.LANE_KEY.match(str(row.get("lane", ""))):
            row["last_seen"] = now
            if name:
                row["lane_name"] = name
        else:
            row = {"lane": key_of(name, session_id), "lane_name": name, "first_seen": now, "last_seen": now}
        m[session_id] = row
        store.write_json_atomic(map_path(), m)
    return dict(row)


# ---------------------------------------------------------------- G3.7

def find(flag=None, environ=None):
    """G3.7: --lane, then PITBOARD_LANE, then CLAUDE_CODE_SESSION_ID in lanes.json; else NoLane."""
    env = os.environ if environ is None else environ
    for value in (flag, env.get("PITBOARD_LANE")):
        if value:
            if not contract.LANE_KEY.match(value):
                raise NoLane(f"pitboard: not a lane key: {value}")
            return value
    sid = env.get("CLAUDE_CODE_SESSION_ID")
    if sid:
        row = read_map().get(sid)
        if isinstance(row, dict) and contract.LANE_KEY.match(str(row.get("lane", ""))):
            return row["lane"]
    keys = ", ".join(store.lane_keys()) or "none yet"
    raise NoLane(f"pitboard: which lane? Pass --lane KEY. Lanes on this machine: {keys}")
