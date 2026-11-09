"""Convert canonical documents into API shapes (single place, no duplication)."""

from __future__ import annotations

from typing import Any

from app.schemas.api import (
    EntityRefOut,
    ResourceOut,
    SessionDetail,
    SessionSummary,
    SpeakerBrief,
    SpeakerOut,
)

_TECH_TYPES = {"technology", "project"}


def speaker_brief(doc: dict[str, Any]) -> SpeakerBrief:
    return SpeakerBrief(
        id=doc["id"],
        full_name=doc["full_name"],
        company=doc.get("company"),
        job_title=doc.get("job_title"),
        photo_url=doc.get("photo_url"),
    )


def _refs(doc: dict[str, Any], types: set[str], limit: int = 8) -> list[EntityRefOut]:
    return [EntityRefOut(**e) for e in doc.get("entities", []) if e["type"] in types][:limit]


def session_summary(doc: dict[str, Any], speakers: dict[str, dict[str, Any]]) -> SessionSummary:
    t = doc.get("time") or {}
    room = doc.get("room") or {}
    return SessionSummary(
        id=doc["id"],
        conference_id=doc["conference_id"],
        title=doc["title"],
        track=doc.get("track"),
        format=doc["format"],
        audience_level=doc.get("audience_level"),
        starts_at=t.get("starts_at"),
        ends_at=t.get("ends_at"),
        starts_at_local=t.get("starts_at_local"),
        day=t.get("day"),
        duration_minutes=t.get("duration_minutes"),
        room=room.get("name"),
        venue=room.get("venue"),
        speakers=[speaker_brief(speakers[i]) for i in doc.get("speaker_ids", []) if i in speakers],
        topics=_refs(doc, {"topic"}),
        technologies=_refs(doc, _TECH_TYPES),
        flags=doc.get("flags", []),
        is_content=doc.get("is_content", True),
        has_resources=bool(doc.get("resources")),
    )


def session_detail(
    doc: dict[str, Any], speakers: dict[str, dict[str, Any]], related: list[Any]
) -> SessionDetail:
    base = session_summary(doc, speakers)
    prov = doc.get("provenance", {})
    return SessionDetail(
        **base.model_dump(),
        description=doc.get("description"),
        subtopics=doc.get("subtopics", []),
        format_origin=doc.get("format_origin", "default"),
        entities=[EntityRefOut(**e) for e in doc.get("entities", [])],
        resources=[
            ResourceOut(kind=r["kind"], url=r["url"], title=r.get("title"))
            for r in doc.get("resources", [])
        ],
        source={
            "system": prov.get("source_system"),
            "source_id": prov.get("source_id"),
            "source_url": prov.get("source_url"),
            "ingested_at": prov.get("ingested_at"),
            "ingestion_version": prov.get("ingestion_version"),
        },
        related=related,
    )


def speaker_out(doc: dict[str, Any]) -> SpeakerOut:
    return SpeakerOut(
        **speaker_brief(doc).model_dump(),
        tagline=doc.get("tagline"),
        bio=doc.get("bio"),
        is_top_speaker=doc.get("is_top_speaker", False),
        links=[
            ResourceOut(kind=r["kind"], url=r["url"], title=r.get("title"))
            for r in doc.get("links", [])
        ],
        expertise=[EntityRefOut(**e) for e in doc.get("entities", [])],
        session_count=len(doc.get("session_ids", [])),
    )
