"""G4: time. Test names carry the codon IDs (plan rule 2)."""
from datetime import datetime, timedelta, timezone

import pytest

from pitboard import contract as c
from pitboard import timefmt as t

NY = t.zone("America/New_York")
NOW = datetime(2026, 11, 17, 19, 30, tzinfo=timezone.utc)  # Tue 2:30 PM ET


def test_G4_1_stored_form():
    assert c.TS.match(c.ts_of(NOW)) and c.ts_of(NOW) == "2026-11-17T19:30:00.000Z"


@pytest.mark.parametrize("stored,expect", [
    ("2026-11-18T00:04:00.000Z", "7:04 PM ET"),           # same ET day
    ("2026-11-15T13:00:00.000Z", "Sun 8:00 AM ET"),       # 2 days back
    ("2026-11-20T22:00:00.000Z", "Fri 5:00 PM ET"),       # 3 days ahead
    ("2026-11-03T13:00:00.000Z", "Nov 3 8:00 AM ET"),     # more than 6 days
    ("2026-07-04T16:00:00.000Z", "Jul 4 12:00 PM ET"),    # EDT also shows ET
])
def test_G4_2_shown_times(stored, expect):
    assert t.show(stored, NY, now=NOW) == expect


@pytest.mark.parametrize("zone_name,expect", [
    ("America/Chicago", "CT"), ("America/Denver", "MT"), ("America/Los_Angeles", "PT"),
    ("Europe/London", "GMT"),
])
def test_G4_2_zone_labels(zone_name, expect):
    dt = NOW.astimezone(t.zone(zone_name))
    assert t.label(dt) == expect


@pytest.mark.parametrize("ago,expect", [
    (timedelta(seconds=30), "0m"), (timedelta(minutes=59), "59m"), (timedelta(minutes=60), "1h"),
    (timedelta(hours=47, minutes=59), "47h"), (timedelta(hours=48), "2d"), (timedelta(days=9), "9d"),
    (timedelta(minutes=-5), "0m"),
])
def test_G4_3_ages(ago, expect):
    assert t.age(c.ts_of(NOW - ago), now=NOW) == expect


@pytest.mark.parametrize("text,expect", [
    ("2026-11-20T17:00:00-05:00", "2026-11-20T22:00:00.000Z"),
    ("2026-11-20T22:00:00Z", "2026-11-20T22:00:00.000Z"),
    ("2026-11-20 17:00", "2026-11-20T22:00:00.000Z"),
    ("2026-11-20", "2026-11-20T22:00:00.000Z"),           # 5:00 PM that day
    ("2026-07-04", "2026-07-04T21:00:00.000Z"),           # 5:00 PM EDT
    ("+30m", "2026-11-17T20:00:00.000Z"),
    ("+2h", "2026-11-17T21:30:00.000Z"),
    ("+3d", "2026-11-20T19:30:00.000Z"),
])
def test_G4_4_deadline_forms(text, expect):
    assert t.parse_deadline(text, NY, now=NOW) == expect


@pytest.mark.parametrize("text", ["tomorrow", "2026-11-20T17:00:00", "Thu 5pm", "+2w", "", "2026-13-01",
                                  "2026-11-20 25:00", None])
def test_G4_4_other_deadlines_refused(text):
    with pytest.raises(t.DeadlineError, match="deadline not understood"):
        t.parse_deadline(text, NY, now=NOW)


def test_G4_5_missing_zone_falls_back_to_local_offset():
    z = t.zone("No/Such_Zone")
    dt = NOW.astimezone(z)
    assert dt.utcoffset() is not None
    lab = t.label(datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=-5))))
    assert lab == "UTC-5"
