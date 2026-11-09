"""Knowledge graph, agenda, assistant and admin routes."""

from __future__ import annotations

import threading
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.agenda.service import AgendaError, AgendaView, Alternative
from app.api.deps import (
    AttendeeDep,
    ConferenceDep,
    ContainerDep,
    OptionalAttendeeDep,
    ReadModelDep,
    admin_dep,
    rate_limit,
)
from app.assistant.service import ChatRequest, ChatResponse
from app.ingestion.snapshot import IngestionStatus, SnapshotStore
from app.knowledge_graph.service import UnknownEntityError
from app.schemas.api import EntityDetail, GraphResponse

router = APIRouter(prefix="/api")


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": f"Unknown entity {exc}"}
    )


# ---- knowledge graph ---------------------------------------------------------------------
@router.get("/knowledge-graph", response_model=GraphResponse)
def graph_overview(
    container: ContainerDep,
    rm: ReadModelDep,
    attendee: OptionalAttendeeDep,
    types: Annotated[list[str] | None, Query(max_length=8)] = None,
    per_type: Annotated[int, Query(ge=3, le=30)] = 10,
    personalized: bool = False,
) -> GraphResponse:
    seeds = None
    if personalized and attendee and attendee.profile:
        seeds = list(attendee.profile.entity_weights())
    return container.graph.overview(rm, types, per_type, seeds)


@router.get("/knowledge-graph/neighborhood/{entity_id}", response_model=GraphResponse)
def graph_neighborhood(
    container: ContainerDep,
    rm: ReadModelDep,
    entity_id: str,
    types: Annotated[list[str] | None, Query(max_length=8)] = None,
    limit: Annotated[int, Query(ge=1, le=40)] = 10,
    include_inferred: bool = True,
) -> GraphResponse:
    try:
        return container.graph.neighborhood(rm, entity_id, types, limit, include_inferred)
    except UnknownEntityError as exc:
        raise _not_found(exc) from exc


@router.get("/knowledge-graph/entities/{entity_id}", response_model=EntityDetail)
def graph_entity(container: ContainerDep, rm: ReadModelDep, entity_id: str) -> EntityDetail:
    try:
        return container.graph.entity_detail(rm, entity_id)
    except UnknownEntityError as exc:
        raise _not_found(exc) from exc


@router.get("/knowledge-graph/path", response_model=GraphResponse)
def graph_path(
    container: ContainerDep,
    rm: ReadModelDep,
    source: Annotated[str, Query(alias="from", max_length=200)],
    target: Annotated[str, Query(alias="to", max_length=200)],
) -> GraphResponse:
    return container.graph.path(rm, source, target)


@router.get("/knowledge-graph/search")
def graph_search(
    container: ContainerDep,
    conf: ConferenceDep,
    q: Annotated[str, Query(max_length=100)] = "",
    types: Annotated[list[str] | None, Query(max_length=8)] = None,
    limit: Annotated[int, Query(ge=1, le=30)] = 10,
):  # type: ignore[no-untyped-def]
    entities = container.search.search_entities(conf.id, q, types, limit)
    speakers = []
    if q and (not types or "speaker" in types):
        speakers = [
            {
                "id": h.id,
                "type": "speaker",
                "name": h.doc["full_name"],
                "session_count": len(h.doc.get("session_ids", [])),
            }
            for h in container.search.search_speakers(conf.id, q, size=5)
        ]
    return {"entities": entities, "speakers": speakers}


# ---- agenda ------------------------------------------------------------------------------
class AddSessionRequest(BaseModel):
    session_id: str = Field(min_length=3, max_length=120)
    note: str | None = Field(default=None, max_length=500)


class ReorderRequest(BaseModel):
    session_ids: list[str] = Field(max_length=200)


def _agenda_error(exc: AgendaError) -> HTTPException:
    code = {"unknown_session": 404, "not_in_agenda": 404, "duplicate": 409, "limit": 422}
    return HTTPException(code.get(exc.code, 400), detail={"code": exc.code, "message": exc.message})


@router.get("/agenda", response_model=AgendaView)
def get_agenda(
    container: ContainerDep, conf: ConferenceDep, rm: ReadModelDep, attendee: AttendeeDep
) -> AgendaView:
    return container.agenda.view(rm, conf, attendee)


@router.post("/agenda/sessions", response_model=AgendaView, status_code=201)
def add_to_agenda(
    body: AddSessionRequest,
    container: ContainerDep,
    conf: ConferenceDep,
    rm: ReadModelDep,
    attendee: AttendeeDep,
) -> AgendaView:
    try:
        state = container.agenda.add(rm, attendee, body.session_id, body.note)
    except AgendaError as exc:
        raise _agenda_error(exc) from exc
    return container.agenda.view(rm, conf, state)


@router.delete("/agenda/sessions/{session_id}", response_model=AgendaView)
def remove_from_agenda(
    session_id: str,
    container: ContainerDep,
    conf: ConferenceDep,
    rm: ReadModelDep,
    attendee: AttendeeDep,
) -> AgendaView:
    try:
        state = container.agenda.remove(attendee, session_id)
    except AgendaError as exc:
        raise _agenda_error(exc) from exc
    return container.agenda.view(rm, conf, state)


@router.put("/agenda/order", response_model=AgendaView)
def reorder_agenda(
    body: ReorderRequest,
    container: ContainerDep,
    conf: ConferenceDep,
    rm: ReadModelDep,
    attendee: AttendeeDep,
) -> AgendaView:
    state = container.agenda.reorder(attendee, body.session_ids)
    return container.agenda.view(rm, conf, state)


@router.post("/agenda/acknowledge-changes", response_model=AgendaView)
def acknowledge_changes(
    container: ContainerDep, conf: ConferenceDep, rm: ReadModelDep, attendee: AttendeeDep
) -> AgendaView:
    state = container.agenda.acknowledge_changes(rm, attendee)
    return container.agenda.view(rm, conf, state)


@router.get("/agenda/conflicts")
def agenda_conflicts(
    container: ContainerDep, conf: ConferenceDep, rm: ReadModelDep, attendee: AttendeeDep
):  # type: ignore[no-untyped-def]
    view = container.agenda.view(rm, conf, attendee)
    return {"conflicts": view.conflicts, "transitions": view.transitions}


@router.get("/agenda/alternatives/{session_id}", response_model=list[Alternative])
def agenda_alternatives(
    session_id: str, container: ContainerDep, rm: ReadModelDep, attendee: AttendeeDep
) -> list[Alternative]:
    try:
        return container.agenda.alternatives(rm, attendee, session_id)
    except AgendaError as exc:
        raise _agenda_error(exc) from exc


@router.get("/agenda/export/ics")
def export_ics(
    container: ContainerDep, conf: ConferenceDep, rm: ReadModelDep, attendee: AttendeeDep
) -> Response:
    body = container.agenda.export_ics(rm, conf, attendee)
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{conf.id}-agenda.ics"'},
    )


# ---- assistant ---------------------------------------------------------------------------
@router.post("/assistant/chat", response_model=ChatResponse, dependencies=[Depends(rate_limit)])
def assistant_chat(
    body: ChatRequest,
    container: ContainerDep,
    conf: ConferenceDep,
    rm: ReadModelDep,
    attendee: OptionalAttendeeDep,
) -> ChatResponse:
    return container.assistant.chat(rm, conf, body, attendee)


# ---- admin -------------------------------------------------------------------------------
class IngestionRequest(BaseModel):
    remote: bool = False
    force: bool = False


_ingest_lock = threading.Lock()


@router.post("/admin/ingestion", status_code=202, dependencies=[Depends(admin_dep)])
def trigger_ingestion(body: IngestionRequest, container: ContainerDep, conf: ConferenceDep):  # type: ignore[no-untyped-def]
    from app.ingestion.pipeline import IngestionPipeline
    from app.search.indexer import Indexer

    if body.remote and not container.settings.allow_remote_refresh:
        raise HTTPException(
            403, detail={"code": "remote_disabled", "message": "Remote refresh is disabled"}
        )
    if not _ingest_lock.acquire(blocking=False):
        raise HTTPException(409, detail={"code": "busy", "message": "Ingestion already running"})

    def run() -> None:
        try:
            pipeline = IngestionPipeline(
                container.settings,
                conf,
                container.vocabulary,
                container.embeddings,
                Indexer(container.es, container.embeddings.dimensions or None),
            )
            pipeline.run(remote=body.remote, force=body.force)
            container.read_models.invalidate(conf.id)
        finally:
            _ingest_lock.release()

    threading.Thread(target=run, daemon=True, name=f"ingest-{conf.id}").start()
    return {"status": "started", "conference_id": conf.id, "remote": body.remote}


@router.get(
    "/admin/ingestion/status",
    response_model=IngestionStatus | None,
    dependencies=[Depends(admin_dep)],
)
def ingestion_status(container: ContainerDep, conf: ConferenceDep) -> IngestionStatus | None:
    return SnapshotStore(container.settings.data_dir / "processed", conf.id).load_status()
