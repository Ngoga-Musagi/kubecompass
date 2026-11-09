"""Recommendation pipeline:

intent/profile -> ES hybrid retrieval -> knowledge-graph expansion (personalized
PageRank) -> configurable scoring -> tiering -> grounded explanations ->
agenda feasibility annotation (kept separate from relevance).
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from app.agenda.scheduling import Slot, conflicts_with
from app.infrastructure.calibration import calibration_for
from app.infrastructure.embeddings import EmbeddingProvider, EmbeddingUnavailableError
from app.knowledge_graph.service import GraphService
from app.knowledge_graph.store import ConferenceReadModel
from app.recommendation.explain import Explanation, explain
from app.recommendation.profile import InterestProfile
from app.recommendation.scoring import (
    Candidate,
    RankingConfig,
    format_fit,
    rescale_cosine,
)
from app.schemas.api import SessionSummary, SpeakerBrief
from app.search.filters import SessionFilters
from app.search.service import SearchService
from app.services.presenters import session_summary, speaker_brief

log = logging.getLogger(__name__)


class AgendaAnnotation(BaseModel):
    in_agenda: bool = False
    conflicts_with: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    session: SessionSummary
    tier: str  # must_attend | highly_relevant | explore
    score: float
    components: dict[str, float]
    explanation: Explanation
    related: list[SessionSummary] = Field(default_factory=list)
    agenda: AgendaAnnotation = Field(default_factory=AgendaAnnotation)


class InsightItem(BaseModel):
    id: str
    name: str
    type: str
    count: int
    detail: str | None = None


class SpeakerInsight(BaseModel):
    speaker: SpeakerBrief
    reason: str
    origin: str


class Insights(BaseModel):
    top_topics: list[InsightItem]
    related_technologies: list[InsightItem]
    speakers: list[SpeakerInsight]
    new_discoveries: list[str]


class RecommendationResponse(BaseModel):
    conference_id: str
    generated_at: datetime
    profile: InterestProfile
    must_attend: list[Recommendation]
    highly_relevant: list[Recommendation]
    explore: list[Recommendation]
    insights: Insights
    weights: dict[str, float]
    pipeline: dict[str, Any]
    degraded: list[str]


def matches_filters(doc: dict[str, Any], f: SessionFilters) -> bool:
    t = doc.get("time") or {}
    if not f.include_non_content and not doc.get("is_content", True):
        return False
    checks = [
        (f.days, t.get("day")),
        (f.tracks, doc.get("track")),
        (f.formats, doc.get("format")),
        (f.audience_levels, doc.get("audience_level")),
    ]
    if any(values and value not in values for values, value in checks):
        return False
    if f.speaker_ids and not set(f.speaker_ids) & set(doc.get("speaker_ids", [])):
        return False
    if f.exclude_ids and doc["id"] in f.exclude_ids:
        return False
    ents = {e["id"] for e in doc.get("entities", [])}
    return all(e in ents for e in f.entity_ids)


class RecommendationService:
    def __init__(
        self,
        search: SearchService,
        graph: GraphService,
        embeddings: EmbeddingProvider,
        config: RankingConfig,
        low_signal: frozenset[str] = frozenset(),
    ) -> None:
        self.low_signal = low_signal
        self.search = search
        self.graph = graph
        self.embeddings = embeddings
        self.cfg = config

    def _embed(self, text: str) -> np.ndarray | None:
        if not text.strip() or not self.embeddings.available:
            return None
        try:
            return self.embeddings.embed_query(text)
        except EmbeddingUnavailableError:
            return None

    def recommend(
        self,
        rm: ConferenceReadModel,
        profile: InterestProfile,
        filters: SessionFilters | None = None,
        agenda_ids: list[str] | None = None,
    ) -> RecommendationResponse:
        t0 = time.perf_counter()
        f = filters or SessionFilters()
        cfg = self.cfg
        w = cfg.weights.normalized()
        degraded: list[str] = []
        # Near-universal entities (e.g. Kubernetes at KubeCon) barely discriminate; damp them.
        weights = {
            k: (v * 0.3 if k in self.low_signal else v) for k, v in profile.entity_weights().items()
        }
        excluded = {i.entity_id for i in profile.excluded_topics if i.entity_id}

        # 1. Hybrid retrieval in Elasticsearch.
        candidates: dict[str, Candidate] = {}
        query = profile.query_text()
        if query:
            result = self.search.search_sessions(
                rm.conference_id,
                query,
                f,
                mode="hybrid",
                size=cfg.retrieval.window,
                vector_text=profile.semantic_text() or None,
            )
            degraded += result.degraded
            for h in result.hits:
                candidates[h.id] = Candidate(
                    session_id=h.id,
                    doc=h.doc,
                    bm25_rank=h.bm25_rank,
                    bm25_score=h.bm25_score,
                    vector_rank=h.vector_rank,
                    highlights=h.highlights,
                )
        retrieved = len(candidates)

        # 2. Graph expansion: personalized PageRank from profile entities (or top hits).
        seeds = dict(weights)
        if not seeds:
            for c in list(candidates.values())[:5]:
                seeds[c.session_id] = 1.0
        ppr = rm.graph.personalized_pagerank(seeds) if seeds else {}
        session_ppr = {k: v for k, v in ppr.items() if k in rm.sessions}
        max_ppr = max(session_ppr.values(), default=0.0) or 1.0
        graph_added = 0
        for sid, _ in sorted(session_ppr.items(), key=lambda kv: -kv[1]):
            if graph_added >= cfg.retrieval.graph_candidates:
                break
            if sid in candidates:
                continue
            doc = rm.sessions[sid]
            if not matches_filters(doc, f):
                continue
            candidates[sid] = Candidate(session_id=sid, doc=doc, from_graph_only=True)
            graph_added += 1

        # 3. Exclusions (explicit "not interested in").
        if excluded:
            for sid in [
                s
                for s, c in candidates.items()
                if any(
                    e["id"] in excluded and e.get("confidence", 1) >= 0.8
                    for e in c.doc.get("entities", [])
                )
            ]:
                del candidates[sid]

        # 4. Score components.
        intent_vec = self._embed(profile.semantic_text())
        goal_vec = self._embed(". ".join(profile.learning_goals))
        if intent_vec is None and query:
            degraded.append("semantic_scoring_unavailable")
        max_bm25 = max((c.bm25_score or 0.0 for c in candidates.values()), default=0.0) or 1.0
        cal = calibration_for(self.embeddings.model_name)
        lo, hi = cal.query_floor, cal.query_ceiling
        for c in candidates.values():
            vec = rm.vector(c.session_id)
            if vec is not None and intent_vec is not None:
                c.intent_similarity = float(vec @ intent_vec)
            if vec is not None and goal_vec is not None:
                c.goal_similarity = float(vec @ goal_vec)
            c.graph_score = session_ppr.get(c.session_id, 0.0) / max_ppr
            bm25n = (c.bm25_score or 0.0) / max_bm25
            sem = rescale_cosine(c.intent_similarity, lo, hi)
            comp = c.components
            comp.interest_match = 0.5 * bm25n + 0.5 * sem if intent_vec is not None else bm25n
            ents = [e for e in c.doc.get("entities", []) if e["id"] not in self.low_signal]
            overlap = sum(
                weights[e["id"]] * e.get("confidence", 1.0) for e in ents if e["id"] in weights
            )
            comp.topic_technology = min(1.0, overlap / 2.0)
            comp.graph_relevance = c.graph_score
            comp.learning_goal = (
                rescale_cosine(c.goal_similarity, lo, hi) if goal_vec is not None else sem
            )
            # Novelty: reachable from the profile (graph or semantics) yet bringing entities
            # the attendee did not mention.
            new_ents = [e for e in ents if e["id"] not in weights]
            frac_new = len(new_ents) / max(1, len(ents)) if ents else 0.0
            reach = max(c.graph_score, sem)
            comp.novelty = reach * frac_new
            comp.format_preference = format_fit(
                c.doc, profile.preferred_formats, profile.experience_level
            )
            c.score = comp.total(w)

        # 5. Tiering (relative to the best score, with an absolute floor).
        ranked = sorted(candidates.values(), key=lambda c: -c.score)
        tiers = cfg.tiers
        top = ranked[0].score if ranked else 0.0
        must: list[Candidate] = []
        high: list[Candidate] = []
        rest: list[Candidate] = []
        for c in ranked:
            if (
                top >= tiers.min_top_score
                and c.score >= tiers.must_attend_ratio * top
                and len(must) < tiers.must_attend_max
                and c.components.topic_technology > 0
            ):
                must.append(c)
            elif (
                c.score >= tiers.highly_relevant_ratio * top
                and len(high) < tiers.highly_relevant_max
            ):
                high.append(c)
            else:
                rest.append(c)
        # Explore: adjacent rather than central: novel, still connected, not already a
        # full topical match.
        explore = sorted(
            (
                c
                for c in rest
                if c.components.novelty >= tiers.explore_min_novelty
                and c.components.topic_technology < 0.75
                and (c.components.graph_relevance >= 0.2 or c.components.learning_goal >= 0.5)
            ),
            key=lambda c: -(0.5 * c.score + 0.5 * c.components.novelty),
        )[: tiers.explore_max]
        # Avoid recommending the same recurring title twice in one tier list.
        must, high, explore = (_dedupe_titles(x) for x in (must, high, explore))

        # 6. Explanations + agenda feasibility (relevance is never changed by feasibility).
        agenda_slots = [
            s
            for s in (Slot.from_doc(rm.sessions[i]) for i in agenda_ids or [] if i in rm.sessions)
            if s
        ]
        agenda_set = set(agenda_ids or [])

        def build(c: Candidate, tier: str) -> Recommendation:
            slot = Slot.from_doc(c.doc)
            related = [r.session for r in self.graph.related_sessions(rm, c.session_id, limit=2)]
            return Recommendation(
                session=session_summary(c.doc, rm.speakers),
                tier=tier,
                score=round(c.score, 4),
                components=c.components.as_dict(),
                explanation=explain(c, profile, tier=tier, low_signal=self.low_signal),
                related=related,
                agenda=AgendaAnnotation(
                    in_agenda=c.session_id in agenda_set,
                    conflicts_with=conflicts_with(slot, agenda_slots) if slot else [],
                ),
            )

        must_r = [build(c, "must_attend") for c in must]
        high_r = [build(c, "highly_relevant") for c in high]
        explore_r = [build(c, "explore") for c in explore]
        insights = self._insights(rm, profile, [*must_r, *high_r, *explore_r])
        return RecommendationResponse(
            conference_id=rm.conference_id,
            generated_at=datetime.now(UTC),
            profile=profile,
            must_attend=must_r,
            highly_relevant=high_r,
            explore=explore_r,
            insights=insights,
            weights=w.model_dump(),
            pipeline={
                "retrieved": retrieved,
                "graph_expanded": graph_added,
                "scored": len(candidates),
                "seed_entities": len(weights),
                "took_ms": int((time.perf_counter() - t0) * 1000),
                "data_version": rm.version,
            },
            degraded=sorted(set(degraded)),
        )

    def _insights(
        self, rm: ConferenceReadModel, profile: InterestProfile, recs: list[Recommendation]
    ) -> Insights:
        weights = profile.entity_weights()
        topic_counts: Counter[str] = Counter()
        tech_counts: Counter[str] = Counter()
        names: dict[str, tuple[str, str]] = {}
        for r in recs:
            doc = rm.sessions[r.session.id]
            for e in doc.get("entities", []):
                names[e["id"]] = (e["name"], e["type"])
                if e["type"] == "topic":
                    topic_counts[e["id"]] += 1
                elif e["id"] not in weights and e["id"] not in self.low_signal:
                    tech_counts[e["id"]] += 1
        top_topics = [
            InsightItem(
                id=i,
                name=names[i][0],
                type=names[i][1],
                count=c,
                detail=f"{c} of your recommendations",
            )
            for i, c in topic_counts.most_common(6)
        ]
        related_tech = [
            InsightItem(
                id=i,
                name=names[i][0],
                type=names[i][1],
                count=c,
                detail=f"Appears in {c} recommended sessions; not in your profile",
            )
            for i, c in tech_counts.most_common(8)
            if c >= 2
        ]
        speakers: dict[str, SpeakerInsight] = {}
        presenting: Counter[str] = Counter()
        for r in recs:
            if r.tier in ("must_attend", "highly_relevant"):
                for sp in r.session.speakers:
                    presenting[sp.id] += 1
        for sp_id, n in presenting.most_common(6):
            if sp_id in rm.speakers:
                speakers[sp_id] = SpeakerInsight(
                    speaker=speaker_brief(rm.speakers[sp_id]),
                    origin="explicit",
                    reason=f"Presents {n} of your top recommendations",
                )
        for eid in list(weights)[:10]:
            for other, data in rm.graph.neighbors(eid):
                if (
                    data["type"] == "WORKS_ON"
                    and other in rm.speakers
                    and other not in speakers
                    and len(speakers) < 10
                ):
                    speakers[other] = SpeakerInsight(
                        speaker=speaker_brief(rm.speakers[other]),
                        origin=data["origin"],
                        reason=f"Works on {rm.entities.get(eid, {}).get('name', eid)}"
                        + (
                            " (stated in bio)"
                            if data["origin"] == "extracted"
                            else " (inferred from Maintainer Track session)"
                        ),
                    )
        return Insights(
            top_topics=top_topics,
            related_technologies=related_tech,
            speakers=list(speakers.values()),
            new_discoveries=[r.session.id for r in recs if r.tier == "explore"][:6],
        )


def _dedupe_titles(items: list[Candidate]) -> list[Candidate]:
    seen: set[str] = set()
    out: list[Candidate] = []
    for c in items:
        key = c.doc["title"].strip().lower()
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out
