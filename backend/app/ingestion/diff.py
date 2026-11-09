"""Detect additions, removals and attendee-relevant modifications between snapshots."""

from __future__ import annotations

from datetime import datetime

from app.domain.models import Session
from app.ingestion.snapshot import SessionChange

# Fields an attendee cares about when a saved session changes.
_WATCHED = ("title", "starts_at", "ends_at", "room", "speakers", "description")


def _view(s: Session) -> dict[str, str | None]:
    return {
        "title": s.title,
        "starts_at": s.time.starts_at_local if s.time else None,
        "ends_at": s.time.ends_at_local if s.time else None,
        "room": s.room.name if s.room else None,
        "speakers": ", ".join(sorted(s.speaker_names)) or None,
        "description": (s.description or "")[:2000] or None,
    }


def diff_sessions(old: list[Session], new: list[Session], now: datetime) -> list[SessionChange]:
    before = {s.id: s for s in old}
    after = {s.id: s for s in new}
    changes: list[SessionChange] = []
    for sid in after.keys() - before.keys():
        changes.append(
            SessionChange(session_id=sid, title=after[sid].title, change="added", detected_at=now)
        )
    for sid in before.keys() - after.keys():
        changes.append(
            SessionChange(
                session_id=sid, title=before[sid].title, change="removed", detected_at=now
            )
        )
    for sid in before.keys() & after.keys():
        b, a = _view(before[sid]), _view(after[sid])
        changed = [f for f in _WATCHED if b[f] != a[f]]
        if changed:
            changes.append(
                SessionChange(
                    session_id=sid,
                    title=after[sid].title,
                    change="modified",
                    fields=changed,
                    before={f: b[f] for f in changed if f != "description"},
                    after={f: a[f] for f in changed if f != "description"},
                    detected_at=now,
                )
            )
    return sorted(changes, key=lambda c: (c.change, c.session_id))
