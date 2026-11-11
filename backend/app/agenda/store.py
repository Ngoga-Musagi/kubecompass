"""Attendee state (profile + agenda) persisted in Elasticsearch.

Guest mode: a random UUID generated in the browser identifies the attendee; no
personal data is collected. The model is calendar-integration ready (each item
keeps the snapshot it was saved with, so later schedule changes are detectable).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from elasticsearch import ApiError, Elasticsearch, NotFoundError, TransportError
from pydantic import BaseModel, Field

from app.agent.permissions import AgentSettings
from app.infrastructure.elasticsearch import (
    SearchUnavailableError,
    alias,
    ensure_state_indices,
    es_call,
)
from app.recommendation.profile import InterestProfile

log = logging.getLogger(__name__)


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
    agent: AgentSettings = Field(default_factory=AgentSettings)
    updated_at: datetime | None = None


class AttendeeStore:
    def __init__(self, es: Elasticsearch) -> None:
        self.es = es
        self._ready = False

    def _ensure(self) -> None:
        if not self._ready:
            es_call(ensure_state_indices, self.es)
            # Indices created before these fields existed: add them (idempotent). A least-privilege
            # key may not manage mappings; that's fine once an admin run has added them.
            try:
                self.es.indices.put_mapping(
                    index=alias("attendees"),
                    properties={
                        "agent": {"type": "object", "enabled": False},
                        "integrations": {"type": "object", "enabled": False},
                    },
                )
            except (ApiError, TransportError) as exc:
                log.warning("Could not update the attendee mapping (needs manage rights): %s", exc)
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
            agent=AgentSettings.model_validate(src["agent"])
            if src.get("agent")
            else AgentSettings(),
            updated_at=src.get("updated_at"),
        )

    # ---- per-person integration records (not event-scoped; same index, own doc id) -----------
    @staticmethod
    def _integration_id(provider: str, guest_id: str) -> str:
        return f"integration:{provider}:{guest_id}"

    def load_integration(self, provider: str, guest_id: str) -> dict[str, Any] | None:
        self._ensure()
        try:
            resp = self.es.get(
                index=alias("attendees"), id=self._integration_id(provider, guest_id)
            )
        except NotFoundError:
            return None
        except (ApiError, TransportError) as exc:
            raise SearchUnavailableError(str(exc)) from exc
        data: dict[str, Any] | None = (resp["_source"].get("integrations") or {}).get(provider)
        return data

    def save_integration(self, provider: str, guest_id: str, data: dict[str, Any]) -> None:
        self._ensure()
        es_call(
            self.es.index,
            index=alias("attendees"),
            id=self._integration_id(provider, guest_id),
            document={
                "guest_id": guest_id,
                "updated_at": datetime.now(UTC).isoformat(),
                "integrations": {provider: data},
            },
            refresh="wait_for",
        )

    def delete_integration(self, provider: str, guest_id: str) -> None:
        self._ensure()
        try:
            self.es.delete(
                index=alias("attendees"),
                id=self._integration_id(provider, guest_id),
                refresh="wait_for",
            )
        except NotFoundError:
            pass
        except (ApiError, TransportError) as exc:
            raise SearchUnavailableError(str(exc)) from exc

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
                "agent": state.agent.model_dump(mode="json"),
            },
            refresh="wait_for",
        )
        return state
