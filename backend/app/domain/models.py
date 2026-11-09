"""Canonical, conference-agnostic domain model.

Every record carries `conference_id` and provenance. Adapters (e.g. Sessionize)
translate source payloads into these models; nothing downstream depends on a
particular source format.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Origin(StrEnum):
    """How a fact or relationship came to exist."""

    EXPLICIT = "explicit"  # supplied directly by the source system
    EXTRACTED = "extracted"  # matched in source text (dictionary / pattern), with evidence
    AI_EXTRACTED = "ai_extracted"  # produced by an LLM; never shown as confirmed fact
    INFERRED = "inferred"  # computed by the application (co-occurrence, similarity)
    CURATED = "curated"  # from the maintained domain vocabulary
    VERIFIED = "verified"  # confirmed against an external source


class Provenance(BaseModel):
    source_system: str
    source_id: str
    source_url: str | None = None
    ingested_at: datetime
    source_updated_at: datetime | None = None
    ingestion_version: str
    payload_hash: str | None = None  # sha256 of the original record (raw kept in data/raw)


class EntityType(StrEnum):
    SESSION = "session"
    SPEAKER = "speaker"
    TOPIC = "topic"
    TECHNOLOGY = "technology"
    PROJECT = "project"
    ORGANIZATION = "organization"
    TRACK = "track"
    ROOM = "room"


class RelationType(StrEnum):
    PRESENTS = "PRESENTS"  # speaker -> session
    ASSOCIATED_WITH = "ASSOCIATED_WITH"  # speaker -> organization
    WORKS_ON = "WORKS_ON"  # speaker -> project
    COVERS = "COVERS"  # session -> topic
    USES = "USES"  # session -> technology
    DISCUSSES = "DISCUSSES"  # session -> project
    BELONGS_TO_TRACK = "BELONGS_TO_TRACK"  # session -> track
    SCHEDULED_IN = "SCHEDULED_IN"  # session -> room
    RELATED_TO = "RELATED_TO"  # entity <-> entity (same or different types)
    PART_OF = "PART_OF"  # technology/project -> topic (curated taxonomy)


class Room(BaseModel):
    id: str
    name: str
    venue: str | None = None  # parsed from "Venue | Level | Room" when present


class Resource(BaseModel):
    kind: str  # slides | repository | demo | website | location_map
    url: str
    title: str | None = None
    origin: Origin = Origin.EXPLICIT


class TimeSlot(BaseModel):
    """Times are stored three ways so nobody confuses local and UTC time."""

    starts_at_local: str  # exactly as the source provides (naive, conference-local)
    ends_at_local: str
    starts_at: datetime  # timezone-aware, conference timezone
    ends_at: datetime
    timezone: str
    day: str  # YYYY-MM-DD in conference timezone
    duration_minutes: int


class EntityRef(BaseModel):
    id: str  # canonical entity id, e.g. "technology:vllm"
    name: str
    type: EntityType
    origin: Origin
    confidence: float = 1.0
    evidence: str | None = None


class Session(BaseModel):
    id: str  # "{conference_id}:{source_id}"
    conference_id: str
    source_id: str
    title: str
    description: str | None
    track: str | None
    subtopics: list[str] = Field(default_factory=list)
    audience_level: str | None = None
    format: str
    format_origin: str  # category | subtopic | title_pattern | default
    flags: list[str] = Field(default_factory=list)
    project_tags: list[str] = Field(default_factory=list)  # explicit source tags
    speaker_ids: list[str] = Field(default_factory=list)
    speaker_names: list[str] = Field(default_factory=list)
    time: TimeSlot | None
    room: Room | None
    resources: list[Resource] = Field(default_factory=list)
    status: str | None = None
    entities: list[EntityRef] = Field(default_factory=list)
    is_content: bool = True  # False for breaks / logistics / expo halls
    provenance: Provenance


class Speaker(BaseModel):
    id: str  # "{conference_id}:{source_id}"
    conference_id: str
    source_id: str
    full_name: str
    first_name: str | None = None
    last_name: str | None = None
    tagline: str | None = None
    bio: str | None = None
    company: str | None = None
    job_title: str | None = None
    photo_url: str | None = None
    is_top_speaker: bool = False
    links: list[Resource] = Field(default_factory=list)
    session_ids: list[str] = Field(default_factory=list)
    entities: list[EntityRef] = Field(default_factory=list)
    provenance: Provenance


class Entity(BaseModel):
    id: str  # "{type}:{slug}"; conference-independent so knowledge carries over
    conference_id: str
    type: EntityType
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    origin: Origin
    session_count: int = 0
    speaker_count: int = 0


class Relationship(BaseModel):
    id: str
    conference_id: str
    source_id: str
    source_type: EntityType
    target_id: str
    target_type: EntityType
    type: RelationType
    origin: Origin
    method: str  # e.g. sessionize_field, vocabulary_match, co_occurrence, embedding_similarity
    confidence: float = 1.0
    evidence: str | None = None
    weight: float = 1.0


class Conference(BaseModel):
    id: str
    name: str
    short_name: str
    city: str
    timezone: str
    website: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    session_count: int = 0
    speaker_count: int = 0
    last_refreshed_at: datetime | None = None
    data_version: str | None = None


class Dataset(BaseModel):
    """A complete, validated, normalized snapshot for one conference."""

    conference: Conference
    sessions: list[Session]
    speakers: list[Speaker]
    entities: list[Entity]
    relationships: list[Relationship]
    rooms: list[Room]
    tracks: list[str]
    issues: list[str] = Field(default_factory=list)  # data-quality findings
    ingestion_version: str
    created_at: datetime
