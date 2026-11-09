"""Ingestion adapter abstraction. One adapter per source platform (Sessionize first)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.config.conferences import ConferenceConfig
from app.domain.models import Room, Session, Speaker


class SourceValidationError(ValueError):
    """Raised when a source payload is structurally invalid or implausibly incomplete."""


@dataclass(frozen=True)
class SourcePayload:
    sessions_raw: bytes
    speakers_raw: bytes
    origin: str  # "local_file" | "remote"
    retrieved_at: datetime
    locations: tuple[str, str]  # where each payload came from (path or URL)


@dataclass
class NormalizedSource:
    sessions: list[Session]
    speakers: list[Speaker]
    rooms: list[Room]
    tracks: list[str]
    issues: list[str] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)


class IngestionAdapter(Protocol):
    name: str

    def load_local(self, conference: ConferenceConfig) -> SourcePayload: ...

    def fetch_remote(self, conference: ConferenceConfig) -> SourcePayload: ...

    def normalize(
        self,
        payload: SourcePayload,
        conference: ConferenceConfig,
        ingested_at: datetime,
        ingestion_version: str,
    ) -> NormalizedSource: ...
