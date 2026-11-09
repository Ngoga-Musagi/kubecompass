"""Discovery: intent parsing, profile, search, suggestions, pathways, recommendations."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import (
    AttendeeDep,
    ConferenceDep,
    ContainerDep,
    OptionalAttendeeDep,
    ReadModelDep,
    rate_limit,
)
from app.knowledge_graph.store import ConferenceReadModel
from app.recommendation.profile import InterestProfile, LLMIntentParser, RuleBasedIntentParser
from app.recommendation.service import RecommendationResponse
from app.schemas.api import (
    FacetValue,
    GraphNodeOut,
    SearchHitOut,
    SearchResponse,
    SessionSummary,
)
from app.search.filters import SessionFilters
from app.services.presenters import session_summary

router = APIRouter(prefix="/api")


class IntentRequest(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
    save: bool = True


class IntentResponse(BaseModel):
    profile: InterestProfile
    parser: str
    llm_available: bool


class SearchRequest(BaseModel):
    query: str = Field(default="", max_length=500)
    filters: SessionFilters = Field(default_factory=SessionFilters)
    mode: Literal["keyword", "vector", "hybrid", "hybrid_native"] = "hybrid"
    offset: int = Field(default=0, ge=0, le=500)
    limit: int = Field(default=20, ge=1, le=100)


class RecommendationRequest(BaseModel):
    profile: InterestProfile | None = None
    filters: SessionFilters = Field(default_factory=SessionFilters)


class Pathway(BaseModel):
    entity: GraphNodeOut
    session_count: int
    profile_match: bool
    children: list[GraphNodeOut]
    sample_sessions: list[SessionSummary]


def _parser(container: ContainerDep, rm: ConferenceReadModel) -> LLMIntentParser:
    available = set(rm.entities)
    rules = RuleBasedIntentParser(container.vocabulary, available)
    catalog = {
        e["name"]: eid
        for eid, e in rm.entities.items()
        if e["type"] in ("topic", "technology", "project") and e.get("session_count", 0) > 0
    }
    return LLMIntentParser(container.llm, rules, catalog)


@router.post("/discovery/intent", response_model=IntentResponse, dependencies=[Depends(rate_limit)])
def parse_intent(
    body: IntentRequest, container: ContainerDep, rm: ReadModelDep, attendee: OptionalAttendeeDep
) -> IntentResponse:
    profile = _parser(container, rm).parse(body.text)
    if body.save and attendee is not None:
        attendee.profile = profile
        container.attendees.save(attendee)
    return IntentResponse(
        profile=profile, parser=profile.parser, llm_available=container.llm.available
    )


@router.get("/profile", response_model=InterestProfile | None)
def get_profile(attendee: AttendeeDep) -> InterestProfile | None:
    return attendee.profile


@router.put("/profile", response_model=InterestProfile)
def put_profile(
    profile: InterestProfile, container: ContainerDep, rm: ReadModelDep, attendee: AttendeeDep
) -> InterestProfile:
    # Keep only entity links that exist in this conference's graph.
    for items in (
        profile.primary_interests,
        profile.secondary_interests,
        profile.preferred_topics,
        profile.preferred_technologies,
        profile.excluded_topics,
    ):
        for i in items:
            if i.entity_id and i.entity_id not in rm.entities:
                i.entity_id = None
    attendee.profile = profile
    container.attendees.save(attendee)
    return profile


@router.post("/discovery/search", response_model=SearchResponse)
def search(
    body: SearchRequest, container: ContainerDep, conf: ConferenceDep, rm: ReadModelDep
) -> SearchResponse:
    result = container.search.search_sessions(
        conf.id, body.query, body.filters, mode=body.mode, size=body.limit, offset=body.offset
    )
    return SearchResponse(
        query=body.query,
        mode=result.mode,
        total=result.total,
        took_ms=result.took_ms,
        degraded=result.degraded,
        hits=[
            SearchHitOut(
                session=session_summary(h.doc, rm.speakers),
                score=h.score,
                bm25_rank=h.bm25_rank,
                vector_rank=h.vector_rank,
                vector_similarity=h.vector_similarity,
                highlights=h.highlights,
            )
            for h in result.hits
        ],
        facets={
            k: [FacetValue(value=v, count=c) for v, c in vals] for k, vals in result.facets.items()
        },
    )


@router.get("/discovery/suggest")
def suggest(
    container: ContainerDep,
    conf: ConferenceDep,
    q: Annotated[str, Query(min_length=1, max_length=100)],
):  # type: ignore[no-untyped-def]
    return container.search.suggest(conf.id, q)


@router.get("/discovery/pathways", response_model=list[Pathway])
def pathways(
    container: ContainerDep,
    rm: ReadModelDep,
    attendee: OptionalAttendeeDep,
    limit: Annotated[int, Query(ge=1, le=24)] = 9,
    min_sessions: int = 4,
) -> list[Pathway]:
    """Topic pathways derived from the data: only topics with real session coverage."""
    from app.knowledge_graph.service import node_out

    profile_ids = set(attendee.profile.entity_weights()) if attendee and attendee.profile else set()
    low = container.vocabulary.low_signal
    topics = [
        e
        for e in rm.entities.values()
        if e["type"] == "topic" and e.get("session_count", 0) >= min_sessions and e["id"] not in low
    ]
    out: list[Pathway] = []
    for t in topics:
        children: list[GraphNodeOut] = []
        sessions: list[tuple[int, float, str]] = []
        for other, data in rm.graph.neighbors(t["id"]):
            if (
                data["type"] == "PART_OF"
                and data["direction"] == "in"
                and other in rm.entities
                and rm.entities[other].get("session_count", 0) > 0
            ):
                children.append(node_out(rm, other))
            elif (
                other in rm.sessions
                and rm.sessions[other].get("is_content", True)
                and data["type"] == "COVERS"
            ):
                rank = 0 if data["origin"] == "explicit" else 1
                sessions.append((rank, -data.get("confidence", 0), other))
        sample = [session_summary(rm.sessions[s], rm.speakers) for *_, s in sorted(sessions)[:3]]
        match = t["id"] in profile_ids or any(c.id in profile_ids for c in children)
        out.append(
            Pathway(
                entity=node_out(rm, t["id"]),
                session_count=t["session_count"],
                profile_match=match,
                children=sorted(children, key=lambda c: -(c.session_count or 0))[:6],
                sample_sessions=sample,
            )
        )
    out.sort(key=lambda p: (not p.profile_match, -p.session_count))
    return out[:limit]


@router.post(
    "/recommendations", response_model=RecommendationResponse, dependencies=[Depends(rate_limit)]
)
def recommendations(
    body: RecommendationRequest,
    container: ContainerDep,
    rm: ReadModelDep,
    attendee: OptionalAttendeeDep,
) -> RecommendationResponse:
    profile = body.profile or (attendee.profile if attendee else None) or InterestProfile()
    agenda_ids = [i.session_id for i in attendee.agenda] if attendee else []
    return container.recommendations.recommend(rm, profile, body.filters, agenda_ids)
