"""Pit Board text views (plan G11 board and list; G10 status joins later).

Every view is plain text cut to a width counted in terminal columns (an emoji
flag takes two). Colour is added last, to the flag only, so cutting never
breaks an ANSI code. Standard library only.
"""
import os
import unicodedata
import math
from datetime import datetime, timedelta, timezone

from . import contract, flags, timefmt

DEFAULT_WIDTH = 100
OPEN_MAX = 30
HISTORY_LIMIT = 50
CUT = contract.CUT_MARK


def cols(text):
    """Terminal columns: wide and emoji characters take two, joiners and marks none."""
    n = 0
    for ch in text:
        if unicodedata.combining(ch) or ch in "‍️":
            continue
        n += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return n


def cut(text, width):
    """Cut to `width` columns, ending with '…' when anything was cut."""
    if cols(text) <= width:
        return text
    out, used = [], 0
    for ch in text:
        w = cols(ch)
        if used + w > width - 1:
            break
        out.append(ch)
        used += w
    return "".join(out) + CUT


def width_of(flag_value=None, environ=None):
    """G11.4: --width, else COLUMNS, else 100."""
    if flag_value:
        return max(20, int(flag_value))
    env = os.environ if environ is None else environ
    try:
        c = int(env.get("COLUMNS", ""))
        if c > 0:
            return max(20, c)
    except ValueError:
        pass
    return DEFAULT_WIDTH


def plain_wanted(plain_flag=False, environ=None):
    """G5.3: NO_COLOR (any value) or --plain."""
    env = os.environ if environ is None else environ
    return bool(plain_flag) or "NO_COLOR" in env


class _Row:
    """One output line: plain text, plus the flag label to colour once the line is cut."""

    def __init__(self, text, label=None, f=None):
        self.text, self.label, self.f = text, label, f

    def out(self, width, plain):
        t = cut(self.text, width)
        if self.label and not plain and self.label in t:
            t = t.replace(self.label, flags.paint(self.label, self.f), 1)
        return t


def _flag(a, now, cfg):
    return flags.flag(a, now, escalate_after_hours=cfg.get("escalate_after_hours", 24),
                      urgent_deadline_hours=cfg.get("urgent_deadline_hours", 24))


def _day(stored, tz):
    dt = contract.parse_ts(stored).astimezone(tz)
    return f"{dt.strftime('%b')} {dt.day}"


def _title(a, tz, now):
    t = a.get("title") or ""
    if a.get("kind") == "hand":
        t = "YOUR HAND: " + t
    if a.get("deadline"):
        t += " · due " + timefmt.show(a["deadline"], tz, now)
    return t


def _second_line(a):
    if a.get("kind") == "hand" and a.get("steps"):
        return "  ".join(f"{i}. {s}" for i, s in enumerate(a["steps"], 1))
    if a.get("suggested"):
        return "→ " + a["suggested"]
    return None


def _answer_hint(asks):
    with_suggested = [a["ask"] for a in asks if a.get("suggested")]
    parts = []
    if with_suggested:
        parts.append("ok " + " ".join(with_suggested))
        parts.append("no " + with_suggested[-1])
    parts.append("or just reply" if parts else "just reply")
    parts.append("pb all = history")
    return "Answer: " + " · ".join(parts)


def board_open(asks, lane_name, tz, now=None, width=DEFAULT_WIDTH, plain=False, cfg=None):
    """G11.1, G11.2, G11.4: the open view."""
    cfg = cfg or {}
    now_dt = now or datetime.now(timezone.utc)
    clock = timefmt.show(contract.ts_of(now_dt), tz, now_dt)
    open_asks = [a for a in asks if a.get("status") == "open"]
    if not open_asks:
        return cut(f"PIT BOARD · {lane_name} · nothing waits on you · {clock}", width)
    ordered = flags.sort_asks(open_asks, "severity", now_dt, escalate_after_hours=cfg.get("escalate_after_hours", 24),
                              urgent_deadline_hours=cfg.get("urgent_deadline_hours", 24))
    shown, more = ordered[:OPEN_MAX], len(ordered) - OPEN_MAX
    fl = {a["uid"]: _flag(a, now_dt, cfg) for a in shown}
    id_w = max(len(a["ask"]) for a in shown)
    word_w = max(len(flags.word(fl[a["uid"]])) for a in shown)
    ages = {a["uid"]: timefmt.age(a["asked_at"], now_dt) for a in shown}
    age_w = max(len(x) for x in ages.values())
    rows = [_Row(f"PIT BOARD · {lane_name} · {len(open_asks)} open · {clock}")]
    for a in shown:
        f = fl[a["uid"]]
        lab = flags.label(f)
        head = f"{a['ask']:<{id_w}} {flags.SYMBOL[f]} {flags.word(f):<{word_w}}  {ages[a['uid']]:<{age_w}}  "
        rows.append(_Row(head + _title(a, tz, now_dt), lab, f))
        second = _second_line(a)
        if second:
            rows.append(_Row(" " * cols(head) + second))
    if more > 0:
        rows.append(_Row(f"(+{more} more: pitboard list)"))
    rows.append(_Row(_answer_hint(shown)))
    return "\n".join(r.out(width, plain) for r in rows)


def _closed_tail(a):
    if a.get("status") == "withdrawn":
        reason = a.get("withdrawn_reason")
        return f" → withdrawn: {reason}" if reason else " → withdrawn"
    if a.get("answer"):
        return f" → {a['answer']} ({a.get('answered_via')})" if a.get("answered_via") else f" → {a['answer']}"
    return ""


def _when(a):
    return (a.get("done_at") or a.get("withdrawn_at") or a.get("answered_at") or a.get("asked_at")) \
        if a.get("status") != "open" else a.get("asked_at")


def history_rows(asks, tz, now_dt, cfg):
    """One line per ask (G11.3): ID, flag, status word, day, title, answer."""
    if not asks:
        return []
    fl = {a["uid"]: _flag(a, now_dt, cfg) for a in asks}
    id_w = max(len(a["ask"]) for a in asks)
    word_w = max(len(flags.word(fl[a["uid"]], a.get("status"))) for a in asks)
    days = {a["uid"]: _day(_when(a), tz) for a in asks}
    day_w = max(len(d) for d in days.values())
    rows = []
    for a in asks:
        f = fl[a["uid"]]
        lab = flags.label(f, a.get("status"))
        word = flags.word(f, a.get("status"))
        text = (f"{a['ask']:<{id_w}} {flags.SYMBOL[f]} {word:<{word_w}}  {days[a['uid']]:<{day_w}}  "
                f"{_title(a, tz, now_dt)}{_closed_tail(a)}")
        rows.append(_Row(text, lab, f))
    return rows


def board_history(asks, lane_name, tz, now=None, width=DEFAULT_WIDTH, plain=False, limit=HISTORY_LIMIT, cfg=None):
    """G11.3, G11.4: every ask, oldest first, the newest `limit` (0 = all); one line each."""
    cfg = cfg or {}
    now_dt = now or datetime.now(timezone.utc)
    clock = timefmt.show(contract.ts_of(now_dt), tz, now_dt)
    ordered = sorted(asks, key=lambda a: (a.get("asked_at") or "", contract.ask_number(a["ask"])))
    total = len(ordered)
    if limit and total > limit:
        ordered = ordered[-limit:]
    head = f"PIT BOARD · {lane_name} · history · {total} asks"
    if len(ordered) < total:
        head += f" (newest {len(ordered)})"
    rows = [_Row(f"{head} · {clock}")] + history_rows(ordered, tz, now_dt, cfg)
    rows.append(_Row("pb = open asks · pitboard show A1 = one ask in full"))
    return "\n".join(r.out(width, plain) for r in rows)


def list_lines(asks, tz, now=None, width=DEFAULT_WIDTH, plain=False, order="severity", cfg=None):
    """pitboard list: one line per ask in the chosen G5.4 order (no header, no hint)."""
    cfg = cfg or {}
    now_dt = now or datetime.now(timezone.utc)
    ordered = flags.sort_asks(asks, order, now_dt, escalate_after_hours=cfg.get("escalate_after_hours", 24),
                              urgent_deadline_hours=cfg.get("urgent_deadline_hours", 24))
    return "\n".join(r.out(width, plain) for r in history_rows(ordered, tz, now_dt, cfg))


def status_segment(state, now=None, plain=False, cfg=None):
    """G10.2: '' when nothing is open; else '<symbol> <n> ask(s) · oldest <age>', coloured
    with the worst flag (a blinking-red ask makes the whole segment blink)."""
    cfg = cfg or {}
    now_dt = now or datetime.now(timezone.utc)
    open_asks = [a for a in (state or {}).get("asks", []) if a.get("status") == "open"]
    if not open_asks:
        return ""
    worst = flags.worst(open_asks, now_dt, escalate_after_hours=cfg.get("escalate_after_hours", 24),
                        urgent_deadline_hours=cfg.get("urgent_deadline_hours", 24))
    n = len(open_asks)
    oldest = min(a["asked_at"] for a in open_asks)
    word = f"{flags.word(worst)} " if plain else ""
    text = f"{flags.SYMBOL[worst]} {word}{n} ask{'s' if n != 1 else ''} · oldest {timefmt.age(oldest, now_dt)}"
    return flags.paint(text, worst, plain)


SEGMENT_NEVER = 9999999999   # P54: the time a segment of no open ask stays true until (seconds, year 2286)


def segment_until(state, now=None, cfg=None):
    """P54: the time (whole seconds since 1970, rounded down) before which status_segment(state, t) is the same text as
    at now: the next change of the oldest ask's age (once a minute under an hour, once an hour under two days, then
    once a day) or of an ask's flag (a deadline coming within urgent_deadline_hours, a can-wait ask reaching
    escalate_after_hours). SEGMENT_NEVER when nothing is open; None when that cannot be worked out."""
    cfg = cfg or {}
    now_dt = now or datetime.now(timezone.utc)
    open_asks = [a for a in (state or {}).get("asks", []) if a.get("status") == "open"]
    if not open_asks:
        return SEGMENT_NEVER
    try:
        oldest = contract.parse_ts(min(a["asked_at"] for a in open_asks))
        secs = max(0.0, (now_dt - oldest).total_seconds())
        step = 60 if secs < 3600 else 3600 if secs < 48 * 3600 else 86400
        marks = [oldest + timedelta(seconds=(int(secs // step) + 1) * step)]
        urgent = float(cfg.get("urgent_deadline_hours", flags.DEFAULT_URGENT_DEADLINE_HOURS))
        escalate = float(cfg.get("escalate_after_hours", flags.DEFAULT_ESCALATE_HOURS))
        for a in open_asks:
            if a.get("deadline"):
                marks.append(contract.parse_ts(a["deadline"]) - timedelta(hours=urgent))
            if a.get("severity") == "can-wait":
                marks.append(contract.parse_ts(a["asked_at"]) + timedelta(hours=escalate))
        until = min(m for m in marks if m > now_dt)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return min(SEGMENT_NEVER, math.floor(until.timestamp()))


REMINDER_MAX_CHARS = 3000


def _reminder_item(a, now_dt, tz, cfg):
    f = _flag(a, now_dt, cfg)
    head = f"- {a['ask']} [{flags.word(f)}, {timefmt.age(a['asked_at'], now_dt)}] "
    if a.get("kind") == "hand":
        text = f"YOUR HAND: {a.get('title')}."
    else:
        text = a.get("title") or ""
        if a.get("suggested"):
            text += f" Suggested: {a['suggested'].rstrip('.')}."
    if a.get("deadline"):
        text += f" Due {timefmt.show(a['deadline'], tz, now_dt)}."
    return head + text


def reminder_text(key, lane_name, machine, asks, tz, now=None, cfg=None):
    """G7.7: the SessionStart reminder for the model. Under 3 000 characters."""
    cfg = cfg or {}
    now_dt = now or datetime.now(timezone.utc)
    op = cfg.get("operator_name") or "you"
    if op.lower() == "you":  # the reminder is read by the model: "you" would mean the agent
        op = "the operator"
    limit = int(cfg.get("reminder_max_items") or 20)
    first = f'Pit Board: you are lane "{lane_name}" (key {key}) on {machine}.'
    rules_add = ("Rules: record every new ask with `pitboard add` before you ask it, and start the question with its ID. "
                 f"That includes an ask only {op} can answer that you send to another agent (a coordinator, a reviewer) "
                 "or a shared board instead of the chat.")                              # plan 1.24, P13
    rules_more = (f"If {op} has answered one, run `pitboard answer <ID> --by operator --answer \"...\"`. "
                  "If it no longer matters, `pitboard withdraw <ID> --reason \"...\"`. "
                  "Do not ask again in chat unless it still blocks your next step.")
    open_asks = flags.sort_asks([a for a in asks if a.get("status") == "open"], "severity", now_dt,
                                escalate_after_hours=cfg.get("escalate_after_hours", 24),
                                urgent_deadline_hours=cfg.get("urgent_deadline_hours", 24))
    page = sorted((a for a in asks if a.get("status") == "answered" and a.get("answered_via") == "page"),
                  key=lambda a: contract.ask_number(a["ask"]))
    if not open_asks and not page:
        return f"{first}\n{rules_add}"
    n = len(open_asks)
    head = f"{first} {n} ask{'s' if n != 1 else ''} wait{'s' if n == 1 else ''} on {op}:" if n else first
    page_lines = [f'Answered on the master list, not done yet: {a["ask"]} → "{a.get("answer")}"' for a in page]
    shown = min(limit, n)
    while True:
        items = [_reminder_item(a, now_dt, tz, cfg) for a in open_asks[:shown]]
        more = [f"(+{n - shown} more: pitboard list)"] if n > shown else []
        text = "\n".join([head] + items + more + page_lines + [rules_add, rules_more])
        if len(text) < REMINDER_MAX_CHARS or shown == 0:
            break
        shown -= 1
    if len(text) >= REMINDER_MAX_CHARS:
        text = text[: REMINDER_MAX_CHARS - 1] + CUT
    return text
