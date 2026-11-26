"""Pit Board contract: the event format (plan G1) and secret masking (plan G19).

This module is the one implementation of the format. The lane store, the hub
and every view use it, so a lane log is read the same way everywhere.
Standard library only.
"""
import json
import re
import uuid
from datetime import datetime, timezone

V = 1
TYPES = ("asked", "updated", "answered", "done", "withdrawn", "reopened")
KINDS = ("question", "decision", "permission", "hand")
SEVERITIES = ("urgent", "blocking", "can-wait")
SOURCES = ("agent", "question-box", "permission", "stop-catch", "operator")
VIAS = ("ok", "no", "text", "page", "question-box", "permission")
BYS = ("agent", "operator", "hook")
ORIGINS = ("lane", "hub")
STATUSES = ("open", "answered", "done", "withdrawn")

MAX_LINE_BYTES = 16384
CUT_MARK = "…"

HEX32 = re.compile(r"^[0-9a-f]{32}$")
ASK_ID = re.compile(r"^A[1-9][0-9]*$")
MACHINE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
LANE_KEY = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
WHERE_TOKEN = re.compile(r"^[A-Za-z0-9._%:@-]{1,64}$")
WHERE_KEYS = ("cwd", "host", "tmux_session", "tmux_window", "tmux_pane")

ENVELOPE_KEYS = ("v", "event_id", "type", "uid", "ask", "lane", "lane_name", "machine",
                 "session_id", "ts", "origin", "by", "data")

# (field, min chars, max chars) for each text field, by event type (G1.3 to G1.8)
TEXT_LIMITS = {
    "title": (1, 120), "detail": (0, 2000), "why": (0, 500), "suggested": (0, 500),
    "answer": (1, 2000), "note": (0, 500), "reason": (1, 500),
}
STEP_MAX = 200
STEPS_MAX_ITEMS = 10
LANE_NAME_MAX = 120
WHERE_TEXT_MAX = 500
MUTABLE = ("severity", "title", "detail", "why", "suggested", "steps", "deadline")


class ContractError(ValueError):
    """An event that breaks the contract. str(err) is one line for a person."""


# ---------------------------------------------------------------- time and ids

def ts_of(dt):
    """A datetime as the stored UTC form YYYY-MM-DDTHH:MM:SS.mmmZ (INV4)."""
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def now_ts():
    return ts_of(datetime.now(timezone.utc))


def parse_ts(text):
    """The stored form back to an aware UTC datetime. ValueError if malformed."""
    if not isinstance(text, str) or not TS.match(text):
        raise ValueError(f"not a stored time: {text!r}")
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def new_id():
    return uuid.uuid4().hex


def ask_number(ask_id):
    return int(ask_id[1:]) if isinstance(ask_id, str) and ASK_ID.match(ask_id) else 0


def next_ask_id(events):
    """G1.12: A + (1 + highest number used by any asked event), never reused."""
    top = 0
    for ev in events:
        if isinstance(ev, dict) and ev.get("type") == "asked":
            top = max(top, ask_number(ev.get("ask")))
    return f"A{top + 1}"


# ---------------------------------------------------------------- masking (G19)

MASK = "[masked]"
_MASK_RULES = [
    # private key blocks; with no END line, to the end of the field
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:.*?-----END [A-Z ]*PRIVATE KEY-----|.*\Z)", re.S), MASK),
    # credentials in URLs
    (re.compile(r"://[^/\s:@]+:[^@\s]+@"), "://" + MASK + "@"),
    # known token shapes
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), MASK),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), MASK),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), MASK),
    (re.compile(r"github_pat_[A-Za-z0-9_]{30,}"), MASK),
    (re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"), MASK),
    (re.compile(r"AKIA[0-9A-Z]{16}"), MASK),
    (re.compile(r"AIza[0-9A-Za-z_-]{35}"), MASK),
    (re.compile(r"glpat-[A-Za-z0-9_-]{20,}"), MASK),
    (re.compile(r"npm_[A-Za-z0-9]{36}"), MASK),
    # JWTs
    (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), MASK),
    # key-value secrets, prefixed names and JSON included; keeps the name
    (re.compile(r"(?i)([A-Za-z0-9_.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key)"
                r"[\"']?\s*[:=]\s*)[\"']?[^\s\"',}]+[\"']?"), r"\1" + MASK),
    # bearer headers
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{16,}"), "Bearer " + MASK),
]
_OPAQUE = re.compile(r"[A-Za-z0-9+=_-]{40,}")


def _opaque(m):
    s = m.group(0)
    if any(c.isdigit() for c in s) and any(c.islower() for c in s) and any(c.isupper() for c in s):
        return MASK
    return s


def mask(text):
    """G19.1: replace anything that looks like a secret with [masked], rules in order."""
    if not isinstance(text, str) or not text:
        return text
    for rx, repl in _MASK_RULES:
        text = rx.sub(repl, text)
    return _OPAQUE.sub(_opaque, text)


# ---------------------------------------------------------------- preparing and validating

def cut(text, limit):
    """Cut to at most `limit` characters, ending with the cut mark when cut."""
    if not isinstance(text, str) or len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + CUT_MARK


def clean_where(where):
    """G1.3: keep only known keys; drop (never refuse) values that fail their pattern."""
    if not isinstance(where, dict):
        return {}
    out = {}
    for k in WHERE_KEYS:
        v = where.get(k)
        if not isinstance(v, str) or not v:
            continue
        if k == "cwd":
            if len(v) <= WHERE_TEXT_MAX:
                out[k] = v
        elif WHERE_TOKEN.match(v):
            out[k] = v
    return out


def _mask_data(data):
    out = dict(data)
    for k, v in data.items():
        if isinstance(v, str) and k in TEXT_LIMITS:
            out[k] = mask(v)
        elif k == "steps" and isinstance(v, list):
            out[k] = [mask(s) if isinstance(s, str) else s for s in v]
    if isinstance(out.get("where"), dict):
        w = dict(out["where"])
        if isinstance(w.get("cwd"), str):
            w["cwd"] = mask(w["cwd"])
        out["where"] = clean_where(w)
    return out


def _cut_data(data):
    out = dict(data)
    for k, (_, hi) in TEXT_LIMITS.items():
        if isinstance(out.get(k), str):
            v = out[k].replace("\n", " ") if k == "title" else out[k]
            out[k] = cut(v, hi)
    if isinstance(out.get("steps"), list):
        out["steps"] = [cut(s, STEP_MAX) if isinstance(s, str) else s for s in out["steps"][:STEPS_MAX_ITEMS]]
    return out


def prepare(event, mode="refuse"):
    """G1.9 order on the way in: mask every text field, then (mode "cut") cut to limits,
    then validate. mode "refuse" (commands, MCP) raises ContractError on any limit;
    mode "cut" (hooks, hub) cuts text first. Returns the prepared event."""
    if not isinstance(event, dict):
        raise ContractError("an event must be a JSON object")
    ev = dict(event)
    if isinstance(ev.get("lane_name"), str):
        ev["lane_name"] = mask(ev["lane_name"])
        if mode == "cut":
            ev["lane_name"] = cut(ev["lane_name"], LANE_NAME_MAX)
    if isinstance(ev.get("data"), dict):
        ev["data"] = _mask_data(ev["data"])
        if mode == "cut":
            ev["data"] = _cut_data(ev["data"])
    validate(ev)
    serialize(ev)  # raises when the line would be too long
    return ev


def _text(data, key, errors, required):
    lo, hi = TEXT_LIMITS[key]
    if key not in data or data[key] is None:
        if required:
            errors.append(f"{key} is required")
        return
    v = data[key]
    if not isinstance(v, str):
        errors.append(f"{key} must be text")
    elif len(v) < lo or len(v) > hi:
        errors.append(f"{key} must be {lo} to {hi} characters (it is {len(v)})")
    elif key == "title" and "\n" in v:
        errors.append("title must be one line")


def _deadline(data, errors):
    d = data.get("deadline")
    if d is not None and not (isinstance(d, str) and TS.match(d)):
        errors.append("deadline must be null or a stored UTC time")


def _steps(data, errors, required):
    s = data.get("steps")
    if s is None or s == []:
        if required:
            errors.append("steps are required for a hand item (1 to 10)")
        return
    if not isinstance(s, list) or not 1 <= len(s) <= STEPS_MAX_ITEMS:
        errors.append("steps must be a list of 1 to 10 items")
        return
    for i, item in enumerate(s, 1):
        if not isinstance(item, str) or not 1 <= len(item) <= STEP_MAX:
            errors.append(f"step {i} must be 1 to {STEP_MAX} characters")


def errors_of(ev):
    """Every rule G1.2 to G1.8 the event breaks; an empty list means valid."""
    errors = []
    if not isinstance(ev, dict):
        return ["an event must be a JSON object"]
    for k in ENVELOPE_KEYS:
        if k not in ev:
            errors.append(f"{k} is missing")
    if errors:
        return errors
    if ev["v"] != V or isinstance(ev["v"], bool):
        errors.append(f"v must be {V}")
    for k in ("event_id", "uid"):
        if not (isinstance(ev[k], str) and HEX32.match(ev[k])):
            errors.append(f"{k} must be 32 lowercase hex characters")
    if ev["type"] not in TYPES:
        errors.append("type is not one of " + ", ".join(TYPES))
    if not (isinstance(ev["ask"], str) and ASK_ID.match(ev["ask"])):
        errors.append("ask must look like A12")
    if not (isinstance(ev["lane"], str) and LANE_KEY.match(ev["lane"])):
        errors.append("lane must be a lane key (a-z, 0-9, -)")
    ln = ev["lane_name"]
    if not (isinstance(ln, str) and 1 <= len(ln) <= LANE_NAME_MAX):
        errors.append(f"lane_name must be 1 to {LANE_NAME_MAX} characters")
    if not (isinstance(ev["machine"], str) and MACHINE.match(ev["machine"])):
        errors.append("machine must match [a-z0-9][a-z0-9-]{0,62}")
    if ev["session_id"] is not None and not isinstance(ev["session_id"], str):
        errors.append("session_id must be text or null")
    if not (isinstance(ev["ts"], str) and TS.match(ev["ts"])):
        errors.append("ts must be YYYY-MM-DDTHH:MM:SS.mmmZ")
    if ev["origin"] not in ORIGINS:
        errors.append("origin must be lane or hub")
    if ev["by"] not in BYS:
        errors.append("by must be agent, operator or hook")
    data = ev["data"]
    if not isinstance(data, dict):
        return errors + ["data must be an object"]
    t = ev["type"]
    if t == "asked":
        kind = data.get("kind")
        if kind not in KINDS:
            errors.append("kind must be one of " + ", ".join(KINDS))
        if data.get("severity") not in SEVERITIES:
            errors.append("severity must be one of " + ", ".join(SEVERITIES))
        if data.get("source") not in SOURCES:
            errors.append("source must be one of " + ", ".join(SOURCES))
        _text(data, "title", errors, True)
        _text(data, "detail", errors, False)
        _text(data, "why", errors, False)
        needs_suggested = kind not in ("hand", "permission")
        _text(data, "suggested", errors, needs_suggested)
        if needs_suggested and data.get("suggested") == "":
            errors.append("suggested is required")
        _steps(data, errors, kind == "hand")
        _deadline(data, errors)
        if "where" in data and not isinstance(data["where"], dict):
            errors.append("where must be an object")
    elif t == "updated":
        keys = [k for k in MUTABLE if k in data]
        if not keys:
            errors.append("an update must change at least one of " + ", ".join(MUTABLE))
        if "severity" in data and data["severity"] not in SEVERITIES:
            errors.append("severity must be one of " + ", ".join(SEVERITIES))
        for k in ("title", "detail", "why", "suggested"):
            if k in data:
                _text(data, k, errors, k == "title")
        if "steps" in data:
            _steps(data, errors, True)
        _deadline(data, errors)
    elif t == "answered":
        _text(data, "answer", errors, True)
        if data.get("via") not in VIAS:
            errors.append("via must be one of " + ", ".join(VIAS))
    elif t == "done":
        _text(data, "note", errors, False)
    elif t in ("withdrawn", "reopened"):
        _text(data, "reason", errors, True)
    return errors


def validate(ev):
    errs = errors_of(ev)
    if errs:
        raise ContractError("; ".join(errs))
    return ev


def is_valid(ev):
    return not errors_of(ev)


# ---------------------------------------------------------------- lines

# P75: characters some line readers (Python's splitlines among them) take as a line end. json.dumps with
# ensure_ascii off leaves them raw, and only inside strings, so they are written as their \\u forms.
LINE_BREAKS_KEPT_RAW = {"\u2028": "\\u2028", "\u2029": "\\u2029", "\u0085": "\\u0085"}


def serialize(ev):
    """G1.1: one line, UTF-8, compact, ensure_ascii off; refused over 16 384 bytes. P75: U+2028, U+2029 and
    U+0085 are written as \\u escapes, so one event is one line for any reader."""
    line = json.dumps(ev, ensure_ascii=False, separators=(",", ":"))
    for ch, esc in LINE_BREAKS_KEPT_RAW.items():
        line = line.replace(ch, esc)
    line += "\n"
    raw = line.encode("utf-8")
    if len(raw) > MAX_LINE_BYTES:
        raise ContractError(f"the event is {len(raw)} bytes; the limit is {MAX_LINE_BYTES}")
    return raw


def parse_line(line):
    """One log line to an event dict, or None for a torn, blank or non-object line."""
    if isinstance(line, bytes):
        try:
            line = line.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not line.endswith("\n"):
        return None  # G2.8: a torn last line is ignored
    line = line.strip()
    if not line:
        return None
    try:
        ev = json.loads(line)
    except ValueError:
        return None
    return ev if isinstance(ev, dict) else None


def read_events(raw):
    """All lines of a log (bytes or str) to (events, bad_count). Bad lines are skipped (INV9).
    P75: a line ends at a line feed only; never splitlines(), which also breaks inside a string at U+2028,
    U+2029, U+0085 and the C0 separators."""
    nl = b"\n" if isinstance(raw, bytes) else "\n"
    events, bad = [], 0
    pieces = raw.split(nl)                       # split the bytes first, then decode each line
    for i, piece in enumerate(pieces):
        if isinstance(piece, bytes):
            piece = piece.decode("utf-8", errors="replace")
        line = piece + "\n" if i < len(pieces) - 1 else piece   # the last piece has no line feed: torn
        if not line.strip():
            continue
        ev = parse_line(line)
        if ev is None:
            if line.endswith("\n"):
                bad += 1
            continue
        events.append(ev)
    return events, bad


# ---------------------------------------------------------------- fold (G1.11)

def _new_state(ev):
    d = ev["data"]
    return {
        "uid": ev["uid"], "ask": ev["ask"], "lane": ev["lane"], "lane_name": ev["lane_name"],
        "machine": ev["machine"], "status": "open",
        "kind": d.get("kind"), "severity": d.get("severity"), "title": d.get("title"),
        "suggested": d.get("suggested") or "", "steps": list(d.get("steps") or []),
        "deadline": d.get("deadline"), "detail": d.get("detail") or "", "why": d.get("why") or "",
        "asked_at": ev["ts"], "answered_at": None, "answer": None, "answered_by": None,
        "answered_via": None, "done_at": None, "done_note": None, "withdrawn_at": None,
        "withdrawn_reason": None, "updated_at": ev["ts"], "source": d.get("source"),
        "where": clean_where(d.get("where")), "session_id": ev["session_id"], "events": 1,
    }


def _clear_round(st):
    for k in ("answered_at", "answer", "answered_by", "answered_via", "done_at", "done_note",
              "withdrawn_at", "withdrawn_reason"):
        st[k] = None


def apply_event(asks, ev):
    """Apply one valid event to `asks` (uid -> state) with the G1.11 table, in place.
    Returns True when the event changed something, False when the table says ignore.
    fold() uses it for a whole log; the store uses it for incremental updates (G2.11)."""
    uid, t, d = ev["uid"], ev["type"], ev["data"]
    st = asks.get(uid)
    if st is None:
        if t == "asked":
            asks[uid] = _new_state(ev)
            return True
        return False
    status = st["status"]
    applied = False
    if t == "updated" and status in ("open", "answered"):
        for k in MUTABLE:
            if k in d:
                st[k] = list(d[k]) if k == "steps" else d[k]
        applied = True
    elif t == "answered":
        if status == "open" or (status == "answered" and ev["by"] == "operator" and st["answered_by"] == "agent"):
            st.update(status="answered", answered_at=ev["ts"], answer=d["answer"],
                      answered_by=ev["by"], answered_via=d["via"])
            applied = True
    elif t == "done" and status in ("open", "answered"):
        st.update(status="done", done_at=ev["ts"], done_note=d.get("note", ""))
        applied = True
    elif t == "withdrawn" and status in ("open", "answered"):
        st.update(status="withdrawn", withdrawn_at=ev["ts"], withdrawn_reason=d["reason"])
        applied = True
    elif t == "reopened" and status in ("answered", "done", "withdrawn"):
        _clear_round(st)
        st["status"] = "open"
        applied = True
    if applied:
        st["updated_at"] = ev["ts"]
        st["lane_name"] = ev["lane_name"]
        st["events"] += 1
    return applied


def fold(events):
    """G1.11. Returns (asks, stats): asks maps uid -> state dict in asked order;
    stats counts duplicate, invalid, skipped (newer v or unknown type), ignored and
    applied events, and gives lane_name (the name on the newest valid event),
    last_applied ([ts, event_id] of the newest valid event) and max_ask (G1.12)."""
    stats = {"duplicate": 0, "invalid": 0, "skipped": 0, "ignored": 0, "applied": 0}
    seen, good = set(), []
    for ev in events:
        if not isinstance(ev, dict):
            stats["invalid"] += 1
            continue
        eid = ev.get("event_id")
        if eid in seen:
            stats["duplicate"] += 1
            continue
        if isinstance(ev.get("v"), int) and ev.get("v") > V or (ev.get("v") == V and ev.get("type") not in TYPES):
            stats["skipped"] += 1
            if isinstance(eid, str):
                seen.add(eid)
            continue
        if not is_valid(ev):
            stats["invalid"] += 1
            continue
        seen.add(eid)
        good.append(ev)
    good.sort(key=lambda e: (e["ts"], e["event_id"]))
    stats["lane_name"] = good[-1]["lane_name"] if good else None  # the newest valid event's name
    stats["last_applied"] = [good[-1]["ts"], good[-1]["event_id"]] if good else None
    stats["max_ask"] = max((ask_number(e["ask"]) for e in good if e["type"] == "asked"), default=0)
    asks = {}
    for ev in good:
        stats["applied" if apply_event(asks, ev) else "ignored"] += 1
    stats["doubled"] = doubled_ids(asks.values())
    return asks, stats


def doubled_ids(asks):
    """P75: ask IDs that name more than one ask (only an older copy of Pit Board can have given one out twice)."""
    seen, twice = set(), set()
    for a in asks:
        (twice if a["ask"] in seen else seen).add(a["ask"])
    return sorted(twice, key=ask_number)


def make_event(etype, *, uid, ask, lane, lane_name, machine, session_id, by, data,
               origin="lane", ts=None, event_id=None):
    """Build an envelope (not yet prepared or validated)."""
    return {
        "v": V, "event_id": event_id or new_id(), "type": etype, "uid": uid, "ask": ask,
        "lane": lane, "lane_name": lane_name, "machine": machine, "session_id": session_id,
        "ts": ts or now_ts(), "origin": origin, "by": by, "data": data,
    }
