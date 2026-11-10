"""Public API contracts. Raw source payloads are never exposed."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    offset: int
    limit: int


class ErrorBody(BaseModel):
    code: str
    message: str


class EntityRefOut(BaseModel):
    id: str
    name: str
    type: str
    origin: str
    confidence: float = 1.0
    evidence: str | None = None


class ResourceOut(BaseModel):
    kind: str
    url: str
    title: str | None = None


class SpeakerBrief(BaseModel):
    id: str
    full_name: str
    company: str | None = None
    job_title: str | None = None
    photo_url: str | None = None


class SessionSummary(BaseModel):
    id: str
    conference_id: str
    title: str
    track: str | None
    format: str
    audience_level: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    starts_at_local: str | None
    day: str | None
    duration_minutes: int | None
    room: str | None
    venue: str | None
    speakers: list[SpeakerBrief]
    topics: list[EntityRefOut]
    technologies: list[EntityRefOut]  # technologies + projects
    flags: list[str]
    is_content: bool
    has_resources: bool


class SessionDetail(SessionSummary):
    description: str | None
    subtopics: list[str]
    format_origin: str
    entities: list[EntityRefOut]
    resources: list[ResourceOut]
    source: dict[str, Any]  # provenance summary (no raw payload)
    related: list[RelatedSession]


class RelatedSession(BaseModel):
    session: SessionSummary
    evidence: str | None
    confidence: float
    origin: str


class SearchHitOut(BaseModel):
    session: SessionSummary
    score: float
    bm25_rank: int | None = None
    vector_rank: int | None = None
    vector_similarity: float | None = None
    highlights: list[str] = Field(default_factory=list)


class FacetValue(BaseModel):
    value: str
    count: int


class SearchResponse(BaseModel):
    query: str
    mode: str
    total: int
    took_ms: int
    degraded: list[str]
    hits: list[SearchHitOut]
    facets: dict[str, list[FacetValue]]


class SpeakerOut(SpeakerBrief):
    tagline: str | None = None
    bio: str | None = None
    is_top_speaker: bool = False
    links: list[ResourceOut] = Field(default_factory=list)
    expertise: list[EntityRefOut] = Field(default_factory=list)
    session_count: int = 0


class SpeakerDetail(SpeakerOut):
    sessions: list[SessionSummary]
    works_on: list[EntityRefOut]
    related_speakers: list[SpeakerBrief]


class GraphNodeOut(BaseModel):
    id: str
    type: str
    name: str
    session_count: int | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class GraphEdgeOut(BaseModel):
    id: str
    source: str
    target: str
    type: str
    origin: str
    method: str
    confidence: float
    evidence: str | None = None


class GraphResponse(BaseModel):
    center: str | None
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]
    truncated: dict[str, int] = Field(default_factory=dict)


class EntityDetail(BaseModel):
    entity: GraphNodeOut
    origin: str
    sessions: list[RelatedSession]
    speakers: list[SpeakerBrief]
    related: list[GraphNodeOut]
    parents: list[GraphNodeOut]
    children: list[GraphNodeOut]


class ConferenceOut(BaseModel):
    id: str
    name: str
    short_name: str
    city: str
    timezone: str
    website: str | None
    schedule_url: str | None
    start_date: str | None
    end_date: str | None
    days: list[str]
    session_count: int
    content_session_count: int
    speaker_count: int
    tracks: list[FacetValue]
    formats: list[FacetValue]
    data_version: str | None
    last_refreshed_at: datetime | None
    source_system: str


class IdentityIn(BaseModel):
    handle: str = Field(min_length=1, max_length=254, description="Email address or username")


class IdentityOut(BaseModel):
    attendee_id: str
    kind: Literal["email", "username"]
    display: str


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    elasticsearch: str
    embeddings: str
    llm: str
    indexed_conferences: list[str]


SessionDetail.model_rebuild()
