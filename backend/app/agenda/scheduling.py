"""Pure scheduling logic: overlaps, tight transitions, gaps. Times are tz-aware datetimes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import combinations, pairwise
from typing import Any

# Moving between buildings (e.g. convention center <-> hotel) needs more time
# than moving between rooms in one building. Only used when venue data exists.
MIN_TRANSITION_SAME_VENUE = timedelta(minutes=5)
MIN_TRANSITION_OTHER_VENUE = timedelta(minutes=15)
MIN_GAP = timedelta(minutes=45)


@dataclass(frozen=True)
class Slot:
    session_id: str
    title: str
    start: datetime
    end: datetime
    venue: str | None
    room: str | None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> Slot | None:
        t = doc.get("time")
        if not t:
            return None
        room = doc.get("room") or {}
        return cls(
            doc["id"],
            doc["title"],
            datetime.fromisoformat(t["starts_at"]),
            datetime.fromisoformat(t["ends_at"]),
            room.get("venue"),
            room.get("name"),
        )


def overlaps(a: Slot, b: Slot) -> bool:
    return a.start < b.end and b.start < a.end


@dataclass
class Conflict:
    a: str
    b: str
    overlap_minutes: int


@dataclass
class Transition:
    from_id: str
    to_id: str
    gap_minutes: int
    from_venue: str | None
    to_venue: str | None
    reason: str


@dataclass
class Gap:
    day: str
    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


def find_conflicts(slots: list[Slot]) -> list[Conflict]:
    out: list[Conflict] = []
    for a, b in combinations(sorted(slots, key=lambda s: s.start), 2):
        if overlaps(a, b):
            mins = int((min(a.end, b.end) - max(a.start, b.start)).total_seconds() // 60)
            out.append(Conflict(a.session_id, b.session_id, mins))
    return out


def find_tight_transitions(slots: list[Slot]) -> list[Transition]:
    out: list[Transition] = []
    ordered = sorted(slots, key=lambda s: s.start)
    for a, b in pairwise(ordered):
        if a.start.date() != b.start.date() or overlaps(a, b):
            continue
        gap = b.start - a.end
        if a.venue and b.venue and a.venue != b.venue and gap < MIN_TRANSITION_OTHER_VENUE:
            out.append(
                Transition(
                    a.session_id,
                    b.session_id,
                    int(gap.total_seconds() // 60),
                    a.venue,
                    b.venue,
                    f"Different buildings ({a.venue} → {b.venue}) with "
                    f"{int(gap.total_seconds() // 60)} min between sessions",
                )
            )
        elif gap < MIN_TRANSITION_SAME_VENUE and a.room != b.room:
            out.append(
                Transition(
                    a.session_id,
                    b.session_id,
                    int(gap.total_seconds() // 60),
                    a.venue,
                    b.venue,
                    "Back-to-back sessions in different rooms",
                )
            )
    return out


def find_gaps(slots: list[Slot], min_gap: timedelta = MIN_GAP) -> list[Gap]:
    by_day: dict[str, list[Slot]] = {}
    for s in slots:
        by_day.setdefault(s.start.date().isoformat(), []).append(s)
    gaps: list[Gap] = []
    for day, items in sorted(by_day.items()):
        items.sort(key=lambda s: s.start)
        cursor = items[0].end
        for s in items[1:]:
            if s.start - cursor >= min_gap:
                gaps.append(Gap(day, cursor, s.start))
            cursor = max(cursor, s.end)
    return gaps


def conflicts_with(candidate: Slot, slots: list[Slot]) -> list[str]:
    return [
        s.session_id
        for s in slots
        if s.session_id != candidate.session_id and overlaps(candidate, s)
    ]
