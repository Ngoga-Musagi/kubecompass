"""Attendee state (profile + agenda) persisted in Elasticsearch.

Guest mode: a random UUID generated in the browser identifies the attendee; no
personal data is collected. The model is calendar-integration ready (each item
keeps the snapshot it was saved with, so later schedule changes are detectable).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from elasticsearch import ApiError, Elasticsearch, NotFoundError, TransportError
from pydantic import BaseModel, Field

from app.infrastructure.elasticsearch import (
    SearchUnavailableError,
    alias,
    ensure_state_indices,
    es_call,
)
from app.recommendation.profile import InterestProfile


class SavedSnapshot(BaseModel):
    title: str
    starts_at_local: str | None = None
    ends_at_local: str | None = None
    room: str | None = None


class AgendaItem(BaseModel):
    session_id: str
    added_at: datetime
    snapshot: SavedSnapshot
    note: str | None = Field(default=None, max_length=500)
    position: int = 0  # user ordering within the same time slot (calendar order otherwise)


class AttendeeState(BaseModel):
    conference_id: str
    guest_id: str
    profile: InterestProfile | None = None
    agenda: list[AgendaItem] = Field(default_factory=list)
    updated_at: datetime | None = None


class AttendeeStore:
    def __init__(self, es: Elasticsearch) -> None:
        self.es = es
        self._ready = False

    def _ensure(self) -> None:
        if not self._ready:
            es_call(ensure_state_indices, self.es)
            self._ready = True

    @staticmethod
    def _doc_id(conference_id: str, guest_id: str) -> str:
        return f"{conference_id}:{guest_id}"

    def load(self, conference_id: str, guest_id: str) -> AttendeeState:
        self._ensure()
        try:
            resp = self.es.get(index=alias("attendees"), id=self._doc_id(conference_id, guest_id))
        except NotFoundError:
            return AttendeeState(conference_id=conference_id, guest_id=guest_id)
        except (ApiError, TransportError) as exc:
            raise SearchUnavailableError(str(exc)) from exc
        src: dict[str, Any] = resp["_source"]
        return AttendeeState(
            conference_id=conference_id,
            guest_id=guest_id,
            profile=InterestProfile.model_validate(src["profile"]) if src.get("profile") else None,
            agenda=[
                AgendaItem.model_validate(i) for i in (src.get("agenda") or {}).get("items", [])
            ],
            updated_at=src.get("updated_at"),
        )

    def save(self, state: AttendeeState) -> AttendeeState:
        self._ensure()
        state.updated_at = datetime.now(UTC)
        es_call(
            self.es.index,
            index=alias("attendees"),
            id=self._doc_id(state.conference_id, state.guest_id),
            document={
                "conference_id": state.conference_id,
                "guest_id": state.guest_id,
                "updated_at": state.updated_at.isoformat(),
                "profile": state.profile.model_dump(mode="json") if state.profile else None,
                "agenda": {"items": [i.model_dump(mode="json") for i in state.agenda]},
            },
            refresh="wait_for",
        )
        return state
