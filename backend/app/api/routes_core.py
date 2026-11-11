"""Health, conferences, sessions and speakers."""

from __future__ import annotations

from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import (
    ConferenceDep,
    ContainerDep,
    OptionalAttendeeDep,
    ReadModelDep,
    rate_limit,
)
from app.config.conferences import (
    ConferenceConfig,
    UnknownConferenceError,
    get_conference,
    load_conferences,
)
from app.domain.identity import InvalidHandle, attendee_id_for, masked, normalize_handle
from app.infrastructure.elasticsearch import es_call
from app.ingestion.snapshot import SnapshotStore
from app.knowledge_graph.store import ConferenceReadModel
from app.schemas.api import (
    ConferenceOut,
    EntityRefOut,
    FacetValue,
    HealthOut,
    IdentityIn,
    IdentityOut,
    Page,
    SessionDetail,
    SessionSummary,
    SpeakerDetail,
    SpeakerOut,
)
from app.search.filters import SessionFilters
from app.services.container import Container
from app.services.presenters import session_detail, session_summary, speaker_brief, speaker_out

router = APIRouter(prefix="/api")


@router.post("/identity", response_model=IdentityOut, dependencies=[Depends(rate_limit)])
def identity(body: IdentityIn, container: ContainerDep) -> IdentityOut:
    """Turn an email or username into a personal attendee id (the handle is never stored)."""
    try:
        handle, kind = normalize_handle(body.handle)
    except InvalidHandle as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_handle", "message": str(exc)},
        ) from exc
    secret = container.settings.identity_secret
    return IdentityOut(
        attendee_id=attendee_id_for(handle, secret.get_secret_value().encode() if secret else None),
        kind=kind,
        display=masked(handle, kind),
    )


@router.get("/health", response_model=HealthOut)
def health(container: ContainerDep) -> HealthOut:
    es_state = "ok"
    indexed: list[str] = []
    try:
        es_call(container.es.info)
        for cid in load_conferences():
            if container.read_models.get(cid) is not None:
                indexed.append(cid)
    except Exception:
        es_state = "unavailable"
    return HealthOut(
        status="ok" if es_state == "ok" and indexed else "degraded",
        elasticsearch=es_state,
        embeddings=container.embeddings.model_name
        if container.embeddings.available
        else "unavailable (keyword search only)",
        llm=container.llm.describe(),
        indexed_conferences=indexed,
    )


def _conference_out(
    container: Container, conf: ConferenceConfig, rm: ConferenceReadModel
) -> ConferenceOut:
    docs = list(rm.sessions.values())
    content = [d for d in docs if d.get("is_content", True)]
    status_ = SnapshotStore(container.settings.data_dir / "processed", conf.id).load_status()
    days = sorted({day for d in docs if (day := (d.get("time") or {}).get("day"))})
    return ConferenceOut(
        id=conf.id,
        name=conf.name,
        short_name=conf.short_name,
        city=conf.city,
        timezone=conf.timezone,
        website=conf.website,
        schedule_url=conf.source.schedule_url,
        start_date=days[0] if days else None,
        end_date=days[-1] if days else None,
        days=days,
        session_count=len(docs),
        content_session_count=len(content),
        speaker_count=len(rm.speakers),
        tracks=[
            FacetValue(value=k, count=v)
            for k, v in Counter(d["track"] for d in content if d.get("track")).most_common()
        ],
        formats=[
            FacetValue(value=k, count=v)
            for k, v in Counter(d["format"] for d in content).most_common()
        ],
        data_version=rm.version,
        last_refreshed_at=status_.last_successful_at if status_ else None,
        source_system=conf.source.adapter,
    )


@router.get("/conferences", response_model=list[ConferenceOut])
def list_conferences(container: ContainerDep) -> list[ConferenceOut]:
    out = []
    for conf in load_conferences().values():
        rm = container.read_models.get(conf.id)
        if rm is not None:
            out.append(_conference_out(container, conf, rm))
    return out


@router.get("/conferences/{conference_id}", response_model=ConferenceOut)
def get_conference_route(container: ContainerDep, conference_id: str) -> ConferenceOut:
    try:
        conf = get_conference(conference_id)
    except UnknownConferenceError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "unknown_conference", "message": "Unknown conference"},
        ) from exc
    rm = container.read_models.get(conf.id)
    if rm is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "not_indexed", "message": "Conference data has not been ingested"},
        )
    return _conference_out(container, conf, rm)


@router.get("/sessions", response_model=Page[SessionSummary])
def list_sessions(
    container: ContainerDep,
    conf: ConferenceDep,
    rm: ReadModelDep,
    day: Annotated[list[str] | None, Query()] = None,
    track: Annotated[list[str] | None, Query()] = None,
    format: Annotated[list[str] | None, Query()] = None,
    level: Annotated[list[str] | None, Query()] = None,
    entity: Annotated[list[str] | None, Query()] = None,
    include_non_content: bool = False,
    offset: Annotated[int, Query(ge=0, le=5000)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[SessionSummary]:
    f = SessionFilters(
        days=day or [],
        tracks=track or [],
        formats=format or [],
        audience_levels=level or [],
        entity_ids=entity or [],
        include_non_content=include_non_content,
    )
    hits = container.search.browse_sessions(conf.id, f, size=1000)
    return Page(
        items=[session_summary(h.doc, rm.speakers) for h in hits[offset : offset + limit]],
        total=len(hits),
        offset=offset,
        limit=limit,
    )


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(container: ContainerDep, rm: ReadModelDep, session_id: str) -> SessionDetail:
    doc = rm.sessions.get(session_id)
    if doc is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Session not found"}
        )
    related = container.graph.related_sessions(rm, session_id, limit=6)
    return session_detail(doc, rm.speakers, related)


@router.get("/sessions/{session_id}/alternatives")
def session_alternatives(
    container: ContainerDep, rm: ReadModelDep, session_id: str, attendee: OptionalAttendeeDep
):  # type: ignore[no-untyped-def]
    from app.agenda.service import AgendaError
    from app.agenda.store import AttendeeState

    state = attendee or AttendeeState(conference_id=rm.conference_id, guest_id="anonymous")
    try:
        return container.agenda.alternatives(rm, state, session_id)
    except AgendaError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"code": exc.code, "message": exc.message}
        ) from exc


@router.get("/speakers", response_model=Page[SpeakerOut])
def list_speakers(
    container: ContainerDep,
    conf: ConferenceDep,
    rm: ReadModelDep,
    q: Annotated[str, Query(max_length=200)] = "",
    entity: Annotated[list[str] | None, Query()] = None,
    offset: Annotated[int, Query(ge=0, le=2000)] = 0,
    limit: Annotated[int, Query(ge=1, le=800)] = 30,
) -> Page[SpeakerOut]:
    hits = container.search.search_speakers(
        conf.id, q, size=1000 if not q else 100, entity_ids=entity or []
    )
    items = [speaker_out(h.doc) for h in hits]
    return Page(items=items[offset : offset + limit], total=len(items), offset=offset, limit=limit)


@router.get("/speakers/{speaker_id}", response_model=SpeakerDetail)
def get_speaker(rm: ReadModelDep, speaker_id: str) -> SpeakerDetail:
    doc = rm.speakers.get(speaker_id)
    if doc is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Speaker not found"}
        )
    sessions = [
        session_summary(rm.sessions[s], rm.speakers)
        for s in doc.get("session_ids", [])
        if s in rm.sessions
    ]
    works_on: list[EntityRefOut] = []
    co: Counter[str] = Counter()
    for other, data in rm.graph.neighbors(speaker_id):
        if data["type"] == "WORKS_ON" and other in rm.entities:
            works_on.append(
                EntityRefOut(
                    id=other,
                    name=rm.entities[other]["name"],
                    type=rm.entities[other]["type"],
                    origin=data["origin"],
                    confidence=data.get("confidence", 1.0),
                    evidence=data.get("evidence"),
                )
            )
    for s in doc.get("session_ids", []):
        for sp in (rm.sessions.get(s) or {}).get("speaker_ids", []):
            if sp != speaker_id and sp in rm.speakers:
                co[sp] += 1
    base = speaker_out(doc)
    return SpeakerDetail(
        **base.model_dump(),
        sessions=sessions,
        works_on=works_on,
        related_speakers=[speaker_brief(rm.speakers[s]) for s, _ in co.most_common(8)],
    )
