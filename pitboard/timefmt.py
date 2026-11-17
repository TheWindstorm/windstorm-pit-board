"""Pit Board time (plan G4): UTC inside, the display time zone outside (INV4).

Stored times are UTC strings made by contract.ts_of. This module turns them
into what a person reads, and turns a person's deadline into a stored time.
Standard library only.
"""
import re
import time
from datetime import datetime, timedelta, timezone

from . import contract

US_LABELS = {"EST": "ET", "EDT": "ET", "CST": "CT", "CDT": "CT",
             "MST": "MT", "MDT": "MT", "PST": "PT", "PDT": "PT"}


class DeadlineError(ValueError):
    """A deadline the operator or agent typed that G4.4 does not accept."""


def zone(name=None):
    """G4.5: the display zone; a fixed system-local offset when zone data is missing."""
    if name:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(name)
        except Exception:
            pass
    offset = -(time.altzone if time.daylight and time.localtime().tm_isdst else time.timezone)
    return timezone(timedelta(seconds=offset))


def label(dt):
    """G4.2: the zone label, e.g. ET; a fixed offset shows as UTC-5."""
    name = dt.tzname() or ""
    if name in US_LABELS:
        return US_LABELS[name]
    if name.startswith("UTC") or not name or name[0] in "+-":
        off = dt.utcoffset() or timedelta(0)
        mins = int(off.total_seconds() // 60)
        sign = "+" if mins >= 0 else "-"
        h, m = divmod(abs(mins), 60)
        return f"UTC{sign}{h}" + (f":{m:02d}" if m else "")
    return name


def _clock(dt):
    return dt.strftime("%I:%M %p").lstrip("0")


def show(stored, tz, now=None):
    """G4.2: '7:04 PM ET' today, 'Tue 7:04 PM ET' within 6 days, 'Nov 3 7:04 PM ET' otherwise."""
    dt = contract.parse_ts(stored).astimezone(tz)
    now = (now or datetime.now(timezone.utc)).astimezone(tz)
    lab = label(dt)
    days = abs((dt.date() - now.date()).days)
    if days == 0:
        return f"{_clock(dt)} {lab}"
    if days <= 6:
        return f"{dt.strftime('%a')} {_clock(dt)} {lab}"
    return f"{dt.strftime('%b')} {dt.day} {_clock(dt)} {lab}"


def age(stored, now=None):
    """G4.3: 0m to 59m, 1h to 47h, then 2d and up. Never negative."""
    now = now or datetime.now(timezone.utc)
    secs = max(0, (now - contract.parse_ts(stored)).total_seconds())
    mins = int(secs // 60)
    if mins < 60:
        return f"{mins}m"
    hours = mins // 60
    if hours < 48:
        return f"{hours}h"
    return f"{hours // 24}d"


_REL = re.compile(r"^\+(\d{1,5})([mhd])$")
_LOCAL_DT = re.compile(r"^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})$")
_LOCAL_D = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def _local(tz, y, mo, d, h, mi):
    # zoneinfo resolves a repeated hour (fall back) to its first occurrence (fold 0)
    return datetime(y, mo, d, h, mi).replace(tzinfo=tz)


def parse_deadline(text, tz, now=None):
    """G4.4: ISO 8601 with offset or Z; 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD' (5:00 PM) in the
    display zone; or +Nm, +Nh, +Nd. Returns the stored UTC form; DeadlineError otherwise."""
    if not isinstance(text, str):
        raise DeadlineError(f"deadline not understood: {text!r}")
    t = text.strip()
    now = now or datetime.now(timezone.utc)
    try:
        m = _REL.match(t)
        if m:
            n, unit = int(m.group(1)), m.group(2)
            delta = {"m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}[unit]
            return contract.ts_of(now + delta)
        m = _LOCAL_DT.match(t)
        if m:
            y, mo, d, h, mi = (int(x) for x in m.groups())
            return contract.ts_of(_local(tz, y, mo, d, h, mi))
        m = _LOCAL_D.match(t)
        if m:
            y, mo, d = (int(x) for x in m.groups())
            return contract.ts_of(_local(tz, y, mo, d, 17, 0))
        if "T" in t and (t.endswith("Z") or re.search(r"[+-]\d{2}:\d{2}$", t)):
            dt = datetime.fromisoformat(t[:-1] + "+00:00" if t.endswith("Z") else t)
            if dt.tzinfo is not None:
                return contract.ts_of(dt)
    except (ValueError, OverflowError):
        pass
    raise DeadlineError(f"deadline not understood: {text}")
