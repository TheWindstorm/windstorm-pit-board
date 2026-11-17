"""Pit Board store (plan G2): files, locks, the state cache, and config.

Lane logs are append-only (INV1) and the only truth (INV2); the state cache
is rebuilt from the log after every write and whenever it looks stale.
Standard library only.
"""
import json
import os
import re
import socket
import time

from . import contract, flags

IS_WINDOWS = os.name == "nt"
if IS_WINDOWS:  # pragma: no cover - exercised on Windows only
    import msvcrt
else:
    import fcntl

LOCK_WAIT_COMMAND = 3.0
LOCK_WAIT_HOOK = 1.0
BIG_LOG_BYTES = 20 * 1024 * 1024
LIVE = ("open", "answered")

DEFAULTS = {
    "machine": None,              # filled from the host name
    "operator_name": "you",
    "display_tz": None,           # None = system local zone
    "escalate_after_hours": 24,
    "urgent_deadline_hours": 24,
    "stop_catch": True,
    "hub_url": None,
    "wake": "off",
    "reminder_max_items": 20,
    "self_update": True,
    "update_check_hours": 6,
}
ENV_OVERRIDES = {"PITBOARD_MACHINE": "machine", "PITBOARD_TZ": "display_tz", "PITBOARD_HUB_URL": "hub_url"}


class LaneBusy(RuntimeError):
    """The lane lock was not free in time (exit code 7)."""


# ---------------------------------------------------------------- paths (G2.1, G2.2)

def home():
    return os.environ.get("PITBOARD_HOME") or os.path.join(os.path.expanduser("~"), ".pitboard")


def _mkdir(path):
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def ensure_home():
    h = _mkdir(home())
    for sub in ("lanes", "state", "logs"):
        _mkdir(os.path.join(h, sub))
    return h


def log_path(key):
    return os.path.join(home(), "lanes", key + ".jsonl")


def lock_path(key):
    return os.path.join(home(), "lanes", key + ".lock")


def state_path(key):
    return os.path.join(home(), "state", key + ".json")


# ---------------------------------------------------------------- config (G2.10)

def clean_machine(name):
    name = re.sub(r"[^a-z0-9-]+", "-", (name or "").lower()).strip("-")
    name = re.sub(r"^-+", "", name)[:63]
    return name if contract.MACHINE.match(name or "") else "machine"


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json_atomic(path, obj):
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def config():
    cfg = dict(DEFAULTS)
    user = read_json(os.path.join(home(), "config.json"), {})
    if isinstance(user, dict):
        for k, v in user.items():
            if k in DEFAULTS:
                cfg[k] = v
    for env, key in ENV_OVERRIDES.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    sup = os.environ.get("PITBOARD_SELF_UPDATE")
    if sup in ("0", "1"):
        cfg["self_update"] = sup == "1"
    cfg["machine"] = clean_machine(cfg["machine"] or socket.gethostname().split(".")[0])
    return cfg


# ---------------------------------------------------------------- lock (G2.3)

class LaneLock:
    """Exclusive lock on lanes/<key>.lock; waits up to `timeout` seconds, then LaneBusy."""

    def __init__(self, key, timeout=LOCK_WAIT_COMMAND, path=None):
        self.path = path or lock_path(key)
        self.timeout = timeout
        self.fd = None

    def __enter__(self):
        _mkdir(os.path.dirname(self.path))
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                if IS_WINDOWS:  # pragma: no cover
                    os.lseek(self.fd, 0, 0)
                    msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.monotonic() >= deadline:
                    os.close(self.fd)
                    self.fd = None
                    raise LaneBusy(f"lane busy: {os.path.basename(self.path)}")
                time.sleep(0.02)

    def __exit__(self, *exc):
        if self.fd is not None:
            try:
                if IS_WINDOWS:  # pragma: no cover
                    os.lseek(self.fd, 0, 0)
                    msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self.fd = None
        return False


# ---------------------------------------------------------------- reading (G2.8)

def read_from(key, start=0):
    """Complete lines of the log from byte `start`: (events, bad_count, end), where `end`
    is the offset just after the last complete line (a torn last line is left for later)."""
    try:
        with open(log_path(key), "rb") as f:
            f.seek(start)
            raw = f.read()
    except FileNotFoundError:
        return [], 0, start
    cut = raw.rfind(b"\n") + 1
    events, bad = contract.read_events(raw[:cut])
    return events, bad, start + cut


def read_log(key):
    """(events, bad_line_count). A torn last line is ignored, not counted."""
    events, bad, _ = read_from(key)
    return events, bad


def log_size(key):
    try:
        return os.path.getsize(log_path(key))
    except OSError:
        return 0


def lane_keys():
    try:
        names = os.listdir(os.path.join(home(), "lanes"))
    except OSError:
        return []
    return sorted(n[:-6] for n in names if n.endswith(".jsonl"))


def big_logs():
    """G2.9: lanes whose log passed 20 MB (doctor warns)."""
    return [k for k in lane_keys() if log_size(k) > BIG_LOG_BYTES]


# ---------------------------------------------------------------- the state cache (G2.6, G2.7, G2.11)

class View:
    """What a writer's build function sees (G2.5).

    asks: uid -> state. Live asks only (open or answered) when full is False;
          every ask when full is True (and then events holds every event).
    """

    def __init__(self, asks, max_ask, events=None, full=False):
        self.asks, self.max_ask, self.events, self.full = asks, max_ask, events, full

    def next_ask_id(self):
        return f"A{self.max_ask + 1}"

    def find(self, ask_id):
        for a in self.asks.values():
            if a["ask"] == ask_id:
                return a
        return None


def _key(ev):
    return (ev["ts"], ev["event_id"])


def _state(key, asks, stats, size, cfg, now=None):
    live = [a for a in asks.values() if a["status"] in LIVE]
    open_rows = [a for a in live if a["status"] == "open"]
    return {
        "v": contract.V, "lane": key, "lane_name": stats.get("lane_name") or key,
        "machine": cfg["machine"], "built_at": contract.now_ts(), "log_bytes": size,
        "open": len(open_rows),
        "oldest_open_at": min((a["asked_at"] for a in open_rows), default=None),
        "worst_flag": flags.worst(open_rows, now, escalate_after_hours=cfg["escalate_after_hours"],
                                  urgent_deadline_hours=cfg["urgent_deadline_hours"]),
        "max_ask": stats.get("max_ask", 0), "last_applied": stats.get("last_applied"),
        "stats": {k: v for k, v in stats.items() if k in ("duplicate", "invalid", "skipped", "ignored", "applied")},
        "asks": live,
    }


def _cache_fresh(cache, size):
    return (isinstance(cache, dict) and cache.get("v") == contract.V and cache.get("log_bytes") == size
            and isinstance(cache.get("max_ask"), int) and isinstance(cache.get("asks"), list)
            and "last_applied" in cache)


class _Fold:
    """A whole-log fold that can be extended by the lines added after it (G2.11)."""

    def __init__(self, key):
        self.key = key
        self.events, self.bad, self.end = read_from(key)
        self.asks, self.stats = contract.fold(self.events)

    def catch_up(self):
        """Inside the lock: apply only lines added since the first read; refold if one sorts earlier."""
        more, bad, end = read_from(self.key, self.end)
        self.bad += bad
        self.end = end
        if not more:
            return
        self.events += more
        last = self.stats.get("last_applied")
        valid = [e for e in more if contract.is_valid(e)]
        seen = {e.get("event_id") for e in self.events[: len(self.events) - len(more)]}
        if all(e["event_id"] not in seen and (last is None or list(_key(e)) > last) for e in valid) \
                and len(valid) == len(more):
            for ev in sorted(valid, key=_key):
                self._apply(ev)
        else:
            self.asks, self.stats = contract.fold(self.events)

    def _apply(self, ev):
        k = "applied" if contract.apply_event(self.asks, ev) else "ignored"
        self.stats[k] = self.stats.get(k, 0) + 1
        self.stats["last_applied"] = list(_key(ev))
        self.stats["lane_name"] = ev["lane_name"]
        if ev["type"] == "asked":
            self.stats["max_ask"] = max(self.stats.get("max_ask", 0), contract.ask_number(ev["ask"]))


def rebuild_state(key, cfg=None, lock_timeout=LOCK_WAIT_COMMAND):
    """Fold the log outside the lock, then lock, catch up and write the cache (G2.11)."""
    cfg = cfg or config()
    fold = _Fold(key)
    with LaneLock(key, timeout=lock_timeout):
        fold.catch_up()
        st = _state(key, fold.asks, fold.stats, fold.end, cfg)
        _mkdir(os.path.dirname(state_path(key)))
        write_json_atomic(state_path(key), st)
    return st


def read_state(key, cfg=None, lock_timeout=LOCK_WAIT_COMMAND):
    """G2.7: the cache, rebuilt first when its log_bytes differs from the log on disk.
    If the lock is busy, fold without writing (readers never fail on a busy lane)."""
    cfg = cfg or config()
    st = read_json(state_path(key))
    if _cache_fresh(st, log_size(key)):
        return st
    try:
        return rebuild_state(key, cfg, lock_timeout)
    except LaneBusy:
        fold = _Fold(key)
        return _state(key, fold.asks, fold.stats, fold.end, cfg)


def all_asks(key):
    """Every ask of a lane, closed ones too (history, show, export fold the log)."""
    events, _ = read_log(key)
    return contract.fold(events)[0]


# ---------------------------------------------------------------- writing (G2.3 to G2.5, G2.11)

def _write_lines(key, lines):
    fd = os.open(log_path(key), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        for raw in lines:
            os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)


def append(key, build, mode="refuse", lock_timeout=LOCK_WAIT_COMMAND, cfg=None, full=False):
    """Append events to a lane log under its lock (INV1).

    `build(view)` gets a View (G2.5: it takes the next short ID inside the lock) and
    returns one event or a list. Each is prepared (masked, cut in mode "cut",
    validated) before anything is written; one bad event means nothing is written.
    full=True gives build every ask and event (for reopen, inbox and duplicate checks).
    Returns (written, state)."""
    ensure_home()
    cfg = cfg or config()
    pre = None
    if full or not _cache_fresh(read_json(state_path(key)), log_size(key)):
        pre = _Fold(key)  # outside the lock (G2.11)
    with LaneLock(key, timeout=lock_timeout):
        cache = None if full else read_json(state_path(key))
        if not full and _cache_fresh(cache, log_size(key)):
            asks = {a["uid"]: dict(a) for a in cache["asks"]}
            stats = dict(cache["stats"], max_ask=cache["max_ask"], last_applied=cache["last_applied"],
                         lane_name=cache["lane_name"])
            view = View(asks, cache["max_ask"])
            end = cache["log_bytes"]
        else:
            if pre is None:
                pre = _Fold(key)
            pre.catch_up()
            asks, stats = pre.asks, pre.stats
            view = View(asks, stats.get("max_ask", 0), events=pre.events, full=True)
            end = pre.end
        new = build(view)
        if isinstance(new, dict):
            new = [new]
        prepared = [contract.prepare(ev, mode=mode) for ev in new]
        lines = [contract.serialize(ev) for ev in prepared]
        if lines:
            _write_lines(key, lines)
        end = log_size(key)
        known = set(asks)
        last = stats.get("last_applied")
        incremental = all(
            (last is None or list(_key(ev)) > last) and (ev["type"] == "asked" or ev["uid"] in known)
            for ev in prepared)
        if incremental:
            for ev in sorted(prepared, key=_key):
                k = "applied" if contract.apply_event(asks, ev) else "ignored"
                stats[k] = stats.get(k, 0) + 1
                stats["last_applied"] = list(_key(ev))
                stats["lane_name"] = ev["lane_name"]
                if ev["type"] == "asked":
                    stats["max_ask"] = max(stats.get("max_ask", 0), contract.ask_number(ev["ask"]))
        else:  # rare: an old timestamp, or an event for a closed ask the cache does not hold
            events, _, end = read_from(key)
            asks, stats = contract.fold(events)
        state = _state(key, asks, stats, end, cfg)
        _mkdir(os.path.dirname(state_path(key)))
        write_json_atomic(state_path(key), state)
    return prepared, state
