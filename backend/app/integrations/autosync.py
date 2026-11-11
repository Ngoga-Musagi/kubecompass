"""Opt-in automatic calendar sync after agenda changes.

Runs only when the attendee turned on "keep my calendar updated" *and* granted the
`external_actions` permission *and* has a connected calendar. That switch is the attendee's
standing confirmation; turning it off (or revoking the permission) stops it immediately.
Runs as a background task so saving a session stays fast; failures are recorded in the
connection's `last_sync` and retried by the next sync.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.agent.permissions import Permission
from app.config.conferences import get_conference
from app.integrations.google_calendar import CalendarError

if TYPE_CHECKING:
    from app.agenda.store import AttendeeState
    from app.services.container import Container

log = logging.getLogger(__name__)


def autosync_enabled(container: Container, state: AttendeeState) -> bool:
    a = state.agent
    return (
        a.calendar_autosync
        and a.allows(Permission.EXTERNAL_ACTIONS)
        and container.calendar.connected(state.guest_id)
    )


def run_autosync(container: Container, conference_id: str, guest_id: str) -> None:
    """Background task: re-read the latest state, then sync (idempotent)."""
    try:
        state = container.attendees.load(conference_id, guest_id)
        rm = container.read_models.get(conference_id)
        if rm is None or not autosync_enabled(container, state):
            return
        summary = container.calendar.sync(rm, get_conference(conference_id), state)
        log.info("calendar autosync: %s", summary.message)
    except CalendarError as exc:
        log.warning("calendar autosync failed: %s", exc.code)
    except Exception:  # never let a background sync crash the worker
        log.exception("calendar autosync crashed")
