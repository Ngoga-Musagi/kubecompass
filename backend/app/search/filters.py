"""Structured filters. Applied identically to BM25 and kNN so semantics never override them."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SessionFilters(BaseModel):
    days: list[str] = Field(default_factory=list, description="YYYY-MM-DD, conference-local")
    tracks: list[str] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=list)
    audience_levels: list[str] = Field(default_factory=list)
    speaker_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(
        default_factory=list, description="Sessions linked to ALL of these"
    )
    starts_after: datetime | None = None
    ends_before: datetime | None = None
    exclude_ids: list[str] = Field(default_factory=list)
    include_non_content: bool = False
    has_resources: bool | None = None


def session_filter_clauses(
    conference_id: str, f: SessionFilters
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (filter, must_not) clause lists."""
    clauses: list[dict[str, Any]] = [{"term": {"conference_id": conference_id}}]
    if not f.include_non_content:
        clauses.append({"term": {"is_content": True}})
    for field, values in (
        ("day", f.days),
        ("track", f.tracks),
        ("format", f.formats),
        ("audience_level", f.audience_levels),
        ("speaker_ids", f.speaker_ids),
    ):
        if values:
            clauses.append({"terms": {field: values}})
    for eid in f.entity_ids:
        clauses.append({"term": {"entity_ids": eid}})
    if f.starts_after:
        clauses.append({"range": {"starts_at": {"gte": f.starts_after.isoformat()}}})
    if f.ends_before:
        clauses.append({"range": {"ends_at": {"lte": f.ends_before.isoformat()}}})
    if f.has_resources is not None:
        clauses.append({"term": {"has_resources": f.has_resources}})
    must_not: list[dict[str, Any]] = []
    if f.exclude_ids:
        must_not.append({"ids": {"values": f.exclude_ids}})
    return clauses, must_not


def as_bool_filter(conference_id: str, f: SessionFilters) -> dict[str, Any]:
    flt, must_not = session_filter_clauses(conference_id, f)
    return {"bool": {"filter": flt, "must_not": must_not}}
