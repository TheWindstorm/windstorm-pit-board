"""Pit Board flags (plan G5): the colour an ask shows, and the order asks are listed in.

Flags change with age and deadlines, so they are always worked out at read
time from an ask's folded state (contract.fold). Standard library only.
"""
from datetime import datetime, timezone

from . import contract

BLINK_RED, RED, BLUE, YELLOW, CHEQUERED, GREY = "blinking-red", "red", "blue", "yellow", "chequered", "grey"

# G5.2 rank: lower is worse
RANK = {BLINK_RED: 0, RED: 1, BLUE: 2, YELLOW: 3, CHEQUERED: 4, GREY: 5}
SYMBOL = {BLINK_RED: "\U0001F534", RED: "\U0001F534", BLUE: "\U0001F535", YELLOW: "\U0001F7E1",
          CHEQUERED: "\U0001F3C1", GREY: "⚪"}
ANSI = {BLINK_RED: "\x1b[5;31m", RED: "\x1b[31m", BLUE: "\x1b[34m", YELLOW: "\x1b[33m",
        CHEQUERED: "", GREY: "\x1b[90m"}
RESET = "\x1b[0m"
# G5.3 words used instead of colour
WORD = {BLINK_RED: "BLINK-RED", RED: "RED", BLUE: "BLUE", YELLOW: "YELLOW", CHEQUERED: "DONE", GREY: "GREY"}

DEFAULT_ESCALATE_HOURS = 24
DEFAULT_URGENT_DEADLINE_HOURS = 24


def _hours_between(later, earlier):
    return (later - earlier).total_seconds() / 3600.0


def flag(ask, now=None, escalate_after_hours=DEFAULT_ESCALATE_HOURS,
         urgent_deadline_hours=DEFAULT_URGENT_DEADLINE_HOURS):
    """G5.1: the first matching row, top to bottom."""
    now = now or datetime.now(timezone.utc)
    status = ask.get("status")
    if status in ("answered", "done"):
        return CHEQUERED
    if status == "withdrawn":
        return GREY
    deadline = ask.get("deadline")
    if ask.get("severity") == "urgent":
        return BLINK_RED
    if deadline:
        try:
            if _hours_between(contract.parse_ts(deadline), now) < urgent_deadline_hours:
                return BLINK_RED
        except ValueError:
            pass
    if ask.get("kind") == "hand":
        return BLUE
    if ask.get("severity") == "blocking":
        return RED
    if ask.get("severity") == "can-wait":
        try:
            if _hours_between(now, contract.parse_ts(ask.get("asked_at"))) >= escalate_after_hours:
                return RED
        except ValueError:
            pass
    return YELLOW


def worst(asks, now=None, **kw):
    """The worst flag among open asks, or None when nothing is open."""
    flags = [flag(a, now, **kw) for a in asks if a.get("status") == "open"]
    return min(flags, key=RANK.get) if flags else None


def paint(text, f, plain=False):
    """G5.3: ANSI colour, or nothing when plain (NO_COLOR or --plain)."""
    if plain or not ANSI.get(f):
        return text
    return ANSI[f] + text + RESET


def word(f, status=None):
    """G5.3: the flag in capitals; a chequered ask shows its status (ANSWERED or DONE)."""
    if f == CHEQUERED and status == "answered":
        return "ANSWERED"
    return WORD[f]


def label(f, status=None):
    """The flag as symbol plus word, e.g. '🔴 RED' or '🏁 ANSWERED'. No ANSI codes."""
    return f"{SYMBOL[f]} {word(f, status)}"


def _deadline_key(a):
    d = a.get("deadline")
    return (0, d) if d else (1, "")


def sort_asks(asks, order="severity", now=None, **kw):
    """G5.4 sort orders: severity, deadline, age, lane."""
    asks = list(asks)
    if order == "severity":
        return sorted(asks, key=lambda a: (RANK[flag(a, now, **kw)], _deadline_key(a), a.get("asked_at") or ""))
    if order == "deadline":
        return sorted(asks, key=lambda a: (_deadline_key(a), RANK[flag(a, now, **kw)], a.get("asked_at") or ""))
    if order == "age":
        return sorted(asks, key=lambda a: a.get("asked_at") or "")
    if order == "lane":
        return sorted(asks, key=lambda a: (a.get("machine") or "", (a.get("lane_name") or "").lower(),
                                           contract.ask_number(a.get("ask"))))
    raise ValueError(f"unknown sort order: {order}")
