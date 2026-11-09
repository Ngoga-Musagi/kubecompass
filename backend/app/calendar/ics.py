"""RFC 5545 iCalendar export with a generated VTIMEZONE for the conference zone.

Event times are written in the conference's IANA zone (TZID) and a VTIMEZONE
block is derived from zoneinfo transitions, so calendar clients show the right
local time on every date with no hardcoded offsets.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel


class CalendarEvent(BaseModel):
    uid: str
    title: str
    start: datetime  # tz-aware
    end: datetime
    location: str | None = None
    description: str | None = None
    url: str | None = None


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Fold lines longer than 75 octets (RFC 5545 §3.1)."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts: list[str] = []
    current = b""
    limit = 75
    for ch in line:
        b = ch.encode("utf-8")
        if len(current) + len(b) > limit:
            parts.append(current.decode("utf-8"))
            current = b
            limit = 74  # continuation lines start with a space
        else:
            current += b
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def _fmt_offset(td: timedelta) -> str:
    total = int(td.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{sign}{total // 3600:02d}{(total % 3600) // 60:02d}"


def _transitions(tz: ZoneInfo, start: datetime, end: datetime) -> list[datetime]:
    """UTC instants where the zone's offset changes, found by hourly scan + bisection."""
    out: list[datetime] = []
    t = start
    prev = t.astimezone(tz).utcoffset()
    step = timedelta(hours=6)
    while t < end:
        nxt = t + step
        off = nxt.astimezone(tz).utcoffset()
        if off != prev:
            lo, hi = t, nxt
            while hi - lo > timedelta(minutes=1):
                mid = lo + (hi - lo) / 2
                if mid.astimezone(tz).utcoffset() == prev:
                    lo = mid
                else:
                    hi = mid
            out.append(hi.replace(second=0, microsecond=0))
            prev = off
        t = nxt
    return out


def vtimezone(tzid: str, years: set[int]) -> list[str]:
    tz = ZoneInfo(tzid)
    start = datetime(min(years) - 1, 7, 1, tzinfo=UTC)
    end = datetime(max(years) + 1, 7, 1, tzinfo=UTC)
    lines = ["BEGIN:VTIMEZONE", f"TZID:{tzid}"]
    trans = _transitions(tz, start, end)
    if not trans:  # zone without DST: single STANDARD component
        off = start.astimezone(tz).utcoffset() or timedelta(0)
        lines += [
            "BEGIN:STANDARD",
            "DTSTART:19700101T000000",
            f"TZOFFSETFROM:{_fmt_offset(off)}",
            f"TZOFFSETTO:{_fmt_offset(off)}",
            f"TZNAME:{start.astimezone(tz).tzname()}",
            "END:STANDARD",
        ]
    for instant in trans:
        before = (instant - timedelta(minutes=1)).astimezone(tz)
        after = instant.astimezone(tz)
        off_from = before.utcoffset() or timedelta(0)
        off_to = after.utcoffset() or timedelta(0)
        kind = "DAYLIGHT" if (after.dst() or timedelta(0)) > timedelta(0) else "STANDARD"
        local_start = (instant + off_from).strftime("%Y%m%dT%H%M%S")  # in TZOFFSETFROM time
        lines += [
            f"BEGIN:{kind}",
            f"DTSTART:{local_start}",
            f"TZOFFSETFROM:{_fmt_offset(off_from)}",
            f"TZOFFSETTO:{_fmt_offset(off_to)}",
            f"TZNAME:{after.tzname()}",
            f"END:{kind}",
        ]
    lines.append("END:VTIMEZONE")
    return lines


def build_ics(
    events: list[CalendarEvent], tzid: str, calendar_name: str, now: datetime | None = None
) -> str:
    tz = ZoneInfo(tzid)
    stamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//KubeCompass//Conference Agenda//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(calendar_name)}",
        f"X-WR-TIMEZONE:{tzid}",
    ]
    if events:
        lines += vtimezone(tzid, {e.start.astimezone(tz).year for e in events})
    for e in sorted(events, key=lambda e: e.start):
        lines += [
            "BEGIN:VEVENT",
            f"UID:{e.uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;TZID={tzid}:{e.start.astimezone(tz).strftime('%Y%m%dT%H%M%S')}",
            f"DTEND;TZID={tzid}:{e.end.astimezone(tz).strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{_escape(e.title)}",
        ]
        if e.location:
            lines.append(f"LOCATION:{_escape(e.location)}")
        if e.description:
            lines.append(f"DESCRIPTION:{_escape(e.description)}")
        if e.url:
            lines.append(f"URL:{e.url}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
