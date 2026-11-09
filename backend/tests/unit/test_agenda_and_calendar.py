from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.agenda.scheduling import Slot, find_conflicts, find_gaps, find_tight_transitions
from app.calendar.ics import CalendarEvent, build_ics

DEN = ZoneInfo("America/Denver")


def slot(sid: str, start: str, end: str, venue: str = "Salt Palace", room: str = "250") -> Slot:
    return Slot(
        sid,
        f"Session {sid}",
        datetime.fromisoformat(start).replace(tzinfo=DEN),
        datetime.fromisoformat(end).replace(tzinfo=DEN),
        venue,
        room,
    )


def test_overlap_detection_and_minutes():
    a = slot("a", "2026-11-10T11:00", "2026-11-10T11:30")
    b = slot("b", "2026-11-10T11:15", "2026-11-10T11:45")
    c = slot("c", "2026-11-10T11:30", "2026-11-10T12:00")  # touches a, no overlap
    conflicts = find_conflicts([a, b, c])
    pairs = {(x.a, x.b): x.overlap_minutes for x in conflicts}
    assert pairs == {("a", "b"): 15, ("b", "c"): 15}


def test_tight_transition_between_buildings():
    a = slot("a", "2026-11-10T11:00", "2026-11-10T11:30", venue="Salt Palace")
    b = slot("b", "2026-11-10T11:35", "2026-11-10T12:00", venue="Hyatt Regency")
    t = find_tight_transitions([a, b])
    assert len(t) == 1 and t[0].gap_minutes == 5 and "Different buildings" in t[0].reason


def test_same_building_short_gap_is_fine():
    a = slot("a", "2026-11-10T11:00", "2026-11-10T11:30", room="250")
    b = slot("b", "2026-11-10T11:35", "2026-11-10T12:00", room="251")
    assert find_tight_transitions([a, b]) == []


def test_gaps_found_per_day():
    a = slot("a", "2026-11-10T09:00", "2026-11-10T09:30")
    b = slot("b", "2026-11-10T11:00", "2026-11-10T11:30")
    c = slot("c", "2026-11-11T09:00", "2026-11-11T09:30")
    gaps = find_gaps([a, b, c])
    assert [(g.day, g.minutes) for g in gaps] == [("2026-11-10", 90)]


def _unfold(ics: str) -> list[str]:
    return ics.replace("\r\n ", "").split("\r\n")


def test_ics_is_valid_and_uses_conference_timezone():
    ev = CalendarEvent(
        uid="s1@kubecompass",
        title="GPUs, Schedulers; and \\ more",
        start=datetime(2026, 11, 10, 11, 0, tzinfo=DEN),
        end=datetime(2026, 11, 10, 11, 30, tzinfo=DEN),
        location="Salt Palace | Level 2",
        description="Line 1\nLine 2 " + "x" * 200,
    )
    ics = build_ics([ev], "America/Denver", "Test", now=datetime(2026, 11, 9, tzinfo=UTC))
    lines = _unfold(ics)
    assert ics.endswith("\r\n")
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))
    assert "DTSTART;TZID=America/Denver:20261110T110000" in lines
    assert "SUMMARY:GPUs\\, Schedulers\\; and \\\\ more" in lines
    assert lines.count("BEGIN:VEVENT") == lines.count("END:VEVENT") == 1
    # VTIMEZONE covers the 2026-11-01 DST end: -0600 -> -0700, starting 02:00 local.
    assert "DTSTART:20261101T020000" in lines
    i = lines.index("DTSTART:20261101T020000")
    assert lines[i + 1 : i + 3] == ["TZOFFSETFROM:-0600", "TZOFFSETTO:-0700"]


def test_ics_event_time_is_not_utc_confused():
    # 11:00 MST is 18:00 UTC; the file must keep the wall-clock time with TZID.
    ev = CalendarEvent(
        uid="u",
        title="t",
        start=datetime(2026, 11, 10, 18, 0, tzinfo=UTC),
        end=datetime(2026, 11, 10, 18, 30, tzinfo=UTC),
    )
    lines = _unfold(build_ics([ev], "America/Denver", "T"))
    assert "DTSTART;TZID=America/Denver:20261110T110000" in lines
