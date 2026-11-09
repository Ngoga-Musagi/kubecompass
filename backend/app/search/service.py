"""Session, speaker and entity search on Elasticsearch: BM25, kNN, hybrid (RRF)."""

from __future__ import annotations

import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

from elasticsearch import Elasticsearch

from app.config.settings import Settings
from app.infrastructure.elasticsearch import SearchUnavailableError, alias, es_call
from app.infrastructure.embeddings import EmbeddingProvider, EmbeddingUnavailableError
from app.search.filters import SessionFilters, as_bool_filter, session_filter_clauses
from app.search.fusion import rrf

log = logging.getLogger(__name__)

Mode = Literal["keyword", "vector", "hybrid", "hybrid_native"]
_QUOTED = re.compile(r'"([^"]+)"')
_SESSION_SOURCE = ["doc"]
_HIGHLIGHT = {
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "fields": {
        "title": {"number_of_fragments": 0},
        "description": {"fragment_size": 180, "number_of_fragments": 2},
    },
}


@dataclass
class Hit:
    id: str
    doc: dict[str, Any]
    score: float = 0.0  # fused / primary score
    bm25_rank: int | None = None
    bm25_score: float | None = None
    vector_rank: int | None = None
    vector_similarity: float | None = None  # cosine in [-1, 1]
    highlights: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    hits: list[Hit]
    total: int
    mode: Mode
    took_ms: int
    degraded: list[str] = field(default_factory=list)  # e.g. "vector_unavailable"
    facets: dict[str, list[tuple[str, int]]] = field(default_factory=dict)


def _cos_from_es(score: float) -> float:
    # ES cosine similarity scores are (1 + cos) / 2.
    return 2.0 * score - 1.0


def bm25_session_query(query: str) -> dict[str, Any]:
    phrases = _QUOTED.findall(query)
    free = _QUOTED.sub(" ", query).strip()
    should: list[dict[str, Any]] = []
    must: list[dict[str, Any]] = []
    if free:
        should += [
            {
                "multi_match": {
                    "query": free,
                    "fields": [
                        "title^3",
                        "entity_names^2",
                        "description",
                        "speaker_names^1.5",
                        "track^1.5",
                        "topics^1.5",
                        "technologies^1.5",
                        "projects^1.5",
                    ],
                    "type": "best_fields",
                    "tie_breaker": 0.3,
                    "operator": "or",
                    "minimum_should_match": "1<60%",
                }
            },
            {"match_phrase": {"title": {"query": free, "slop": 2, "boost": 3}}},
            {"match_phrase": {"description": {"query": free, "slop": 3, "boost": 1.5}}},
            {"term": {"title.keyword": {"value": free.lower(), "boost": 10}}},
        ]
    for p in phrases:  # exact phrase search: "..." must appear
        must.append(
            {
                "multi_match": {
                    "query": p,
                    "type": "phrase",
                    "fields": ["title^3", "description", "speaker_names^2"],
                }
            }
        )
    q: dict[str, Any] = {"bool": {}}
    if must:
        q["bool"]["must"] = must
    if should:
        q["bool"]["should"] = should
        if not must:
            q["bool"]["minimum_should_match"] = 1
    return q


class SearchService:
    def __init__(
        self, es: Elasticsearch, embeddings: EmbeddingProvider, settings: Settings
    ) -> None:
        self.es = es
        self.embeddings = embeddings
        self.settings = settings
        self.k = settings.rrf_rank_constant

    # ---- sessions ------------------------------------------------------------------------
    def bm25_sessions(
        self, conference_id: str, query: str, f: SessionFilters, size: int
    ) -> list[Hit]:
        flt, must_not = session_filter_clauses(conference_id, f)
        q = bm25_session_query(query)
        q["bool"]["filter"] = flt
        q["bool"]["must_not"] = must_not
        resp = es_call(
            self.es.search,
            index=alias("sessions"),
            query=q,
            size=size,
            source=_SESSION_SOURCE,
            highlight=_HIGHLIGHT,
        )
        return [
            Hit(
                id=h["_id"],
                doc=h["_source"]["doc"],
                score=h["_score"],
                bm25_rank=i,
                bm25_score=h["_score"],
                highlights=_hl(h),
            )
            for i, h in enumerate(resp["hits"]["hits"], start=1)
        ]

    def knn_sessions(
        self, conference_id: str, vector: list[float], f: SessionFilters, size: int
    ) -> list[Hit]:
        knn = {
            "field": "embedding",
            "query_vector": vector,
            "k": size,
            "num_candidates": max(100, size * 4),
            "filter": as_bool_filter(conference_id, f),
        }
        resp = es_call(
            self.es.search, index=alias("sessions"), knn=knn, size=size, source=_SESSION_SOURCE
        )
        return [
            Hit(
                id=h["_id"],
                doc=h["_source"]["doc"],
                score=_cos_from_es(h["_score"]),
                vector_rank=i,
                vector_similarity=_cos_from_es(h["_score"]),
            )
            for i, h in enumerate(resp["hits"]["hits"], start=1)
        ]

    def _query_vector(self, text: str) -> list[float] | None:
        if not self.embeddings.available:
            return None
        try:
            return self.embeddings.embed_query(text).tolist()
        except EmbeddingUnavailableError:
            return None

    def search_sessions(
        self,
        conference_id: str,
        query: str,
        filters: SessionFilters | None = None,
        mode: Mode = "hybrid",
        size: int = 20,
        offset: int = 0,
        vector_text: str | None = None,
    ) -> SearchResult:
        f = filters or SessionFilters()
        start = time.perf_counter()
        degraded: list[str] = []
        window = max(self.settings.retrieval_window, offset + size)
        query = query.strip()

        if not query:
            hits = self.browse_sessions(conference_id, f, size=window)
            return self._finish(hits, "keyword", start, degraded, offset, size)

        vector = None
        if mode != "keyword":
            vector = self._query_vector(vector_text or query)
            if vector is None:
                degraded.append("vector_unavailable")
                mode = "keyword"

        if mode == "hybrid" and self.settings.fusion_mode == "native":
            mode = "hybrid_native"
        if mode == "keyword":
            hits = self.bm25_sessions(conference_id, query, f, window)
        elif mode == "vector":
            hits = self.knn_sessions(conference_id, vector, f, window)  # type: ignore[arg-type]
        elif mode == "hybrid_native":
            try:
                hits = self._native_rrf(conference_id, query, vector, f, window)  # type: ignore[arg-type]
            except SearchUnavailableError as exc:
                log.warning("Native RRF unavailable (%s); falling back to app-side RRF", exc)
                degraded.append("native_rrf_unavailable")
                hits = self._app_rrf(conference_id, query, vector, f, window)  # type: ignore[arg-type]
                mode = "hybrid"
        else:
            hits = self._app_rrf(conference_id, query, vector, f, window)  # type: ignore[arg-type]
        return self._finish(hits, mode, start, degraded, offset, size)

    def _finish(
        self, hits: list[Hit], mode: Mode, start: float, degraded: list[str], offset: int, size: int
    ) -> SearchResult:
        return SearchResult(
            hits=hits[offset : offset + size],
            total=len(hits),
            mode=mode,
            took_ms=int((time.perf_counter() - start) * 1000),
            degraded=degraded,
            facets=_facets(hits),
        )

    def _app_rrf(
        self, conference_id: str, query: str, vector: list[float], f: SessionFilters, window: int
    ) -> list[Hit]:
        lexical = self.bm25_sessions(conference_id, query, f, window)
        semantic = self.knn_sessions(conference_id, vector, f, window)
        fused = rrf([[h.id for h in lexical], [h.id for h in semantic]], k=self.k)
        merged: dict[str, Hit] = {}
        for h in lexical:
            merged[h.id] = h
        for h in semantic:
            if h.id in merged:
                merged[h.id].vector_rank = h.vector_rank
                merged[h.id].vector_similarity = h.vector_similarity
            else:
                merged[h.id] = h
        for hid, score in fused.items():
            merged[hid].score = score
        return sorted(merged.values(), key=lambda h: -h.score)

    def _native_rrf(
        self, conference_id: str, query: str, vector: list[float], f: SessionFilters, window: int
    ) -> list[Hit]:
        flt, must_not = session_filter_clauses(conference_id, f)
        q = bm25_session_query(query)
        q["bool"]["filter"] = flt
        q["bool"]["must_not"] = must_not
        retriever = {
            "rrf": {
                "retrievers": [
                    {"standard": {"query": q}},
                    {
                        "knn": {
                            "field": "embedding",
                            "query_vector": vector,
                            "k": window,
                            "num_candidates": max(100, window * 4),
                            "filter": as_bool_filter(conference_id, f),
                        }
                    },
                ],
                "rank_window_size": window,
                "rank_constant": self.k,
            }
        }
        resp = es_call(
            self.es.search,
            index=alias("sessions"),
            retriever=retriever,
            size=window,
            source=_SESSION_SOURCE,
        )
        return [
            Hit(id=h["_id"], doc=h["_source"]["doc"], score=h["_score"] or 0.0)
            for h in resp["hits"]["hits"]
        ]

    def browse_sessions(
        self,
        conference_id: str,
        f: SessionFilters,
        size: int = 500,
    ) -> list[Hit]:
        resp = es_call(
            self.es.search,
            index=alias("sessions"),
            query=as_bool_filter(conference_id, f),
            size=size,
            sort=[{"starts_at": "asc"}, {"title.keyword": "asc"}],
            source=_SESSION_SOURCE,
        )
        return [Hit(id=h["_id"], doc=h["_source"]["doc"]) for h in resp["hits"]["hits"]]

    # ---- speakers ------------------------------------------------------------------------
    def search_speakers(
        self, conference_id: str, query: str, size: int = 20, entity_ids: list[str] | None = None
    ) -> list[Hit]:
        flt: list[dict[str, Any]] = [{"term": {"conference_id": conference_id}}]
        for eid in entity_ids or []:
            flt.append({"term": {"entity_ids": eid}})
        if not query.strip():
            resp = es_call(
                self.es.search,
                index=alias("speakers"),
                query={"bool": {"filter": flt}},
                size=size,
                sort=[
                    {"is_top_speaker": "desc"},
                    {"session_count": "desc"},
                    {"full_name.keyword": "asc"},
                ],
                source=["doc"],
            )
            return [Hit(id=h["_id"], doc=h["_source"]["doc"]) for h in resp["hits"]["hits"]]
        bm25 = {
            "bool": {
                "filter": flt,
                "should": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": [
                                "full_name^4",
                                "company^2",
                                "tagline^1.5",
                                "bio",
                                "entity_names^1.5",
                                "session_titles^1.5",
                                "job_title",
                            ],
                            "type": "best_fields",
                            "tie_breaker": 0.3,
                        }
                    },
                    {"match_phrase_prefix": {"full_name": {"query": query, "boost": 5}}},
                ],
                "minimum_should_match": 1,
            }
        }
        lexical = es_call(
            self.es.search, index=alias("speakers"), query=bm25, size=50, source=["doc"]
        )["hits"]["hits"]
        vector = self._query_vector(query)
        semantic: list[dict[str, Any]] = []
        if vector is not None:
            semantic = es_call(
                self.es.search,
                index=alias("speakers"),
                size=50,
                source=["doc"],
                knn={
                    "field": "embedding",
                    "query_vector": vector,
                    "k": 50,
                    "num_candidates": 200,
                    "filter": {"bool": {"filter": flt}},
                },
            )["hits"]["hits"]
        fused = rrf([[h["_id"] for h in lexical], [h["_id"] for h in semantic]], k=self.k)
        docs = {h["_id"]: h["_source"]["doc"] for h in [*lexical, *semantic]}
        vec_rank = {h["_id"]: i for i, h in enumerate(semantic, 1)}
        lex_rank = {h["_id"]: i for i, h in enumerate(lexical, 1)}
        ordered = sorted(fused.items(), key=lambda kv: -kv[1])[:size]
        return [
            Hit(id=i, doc=docs[i], score=s, bm25_rank=lex_rank.get(i), vector_rank=vec_rank.get(i))
            for i, s in ordered
        ]

    # ---- entities / autocomplete ---------------------------------------------------------
    def search_entities(
        self, conference_id: str, query: str, types: list[str] | None = None, size: int = 10
    ) -> list[dict[str, Any]]:
        flt: list[dict[str, Any]] = [
            {"term": {"conference_id": conference_id}},
            {"range": {"session_count": {"gt": 0}}},
        ]
        if types:
            flt.append({"terms": {"type": types}})
        q: dict[str, Any] = {"bool": {"filter": flt}}
        if query.strip():
            q["bool"]["should"] = [
                {
                    "multi_match": {
                        "query": query,
                        "type": "bool_prefix",
                        "fields": ["name.sayt", "name.sayt._2gram", "name.sayt._3gram"],
                    }
                },
                {"match": {"name": {"query": query, "boost": 2}}},
                {"term": {"name.keyword": {"value": query.lower(), "boost": 10}}},
            ]
            q["bool"]["minimum_should_match"] = 1
            sort: list[Any] = ["_score", {"session_count": "desc"}]
        else:
            sort = [{"session_count": "desc"}]
        resp = es_call(self.es.search, index=alias("entities"), query=q, size=size, sort=sort)
        return [h["_source"] for h in resp["hits"]["hits"]]

    def suggest(
        self, conference_id: str, prefix: str, size: int = 5
    ) -> dict[str, list[dict[str, Any]]]:
        def sayt(f):
            return {
                "multi_match": {
                    "query": prefix,
                    "type": "bool_prefix",
                    "fields": [f, f"{f}._2gram", f"{f}._3gram"],
                }
            }

        cflt = {"term": {"conference_id": conference_id}}
        body = [
            {"index": alias("sessions")},
            {
                "query": {
                    "bool": {
                        "filter": [cflt, {"term": {"is_content": True}}],
                        "must": [sayt("title.sayt")],
                    }
                },
                "size": size,
                "_source": ["id", "title", "track", "starts_at_local"],
            },
            {"index": alias("speakers")},
            {
                "query": {"bool": {"filter": [cflt], "must": [sayt("full_name.sayt")]}},
                "size": size,
                "_source": ["id", "full_name", "company"],
            },
        ]
        resp = es_call(self.es.msearch, searches=body)
        sessions, speakers = (r["hits"]["hits"] for r in resp["responses"])
        return {
            "sessions": [h["_source"] for h in sessions],
            "speakers": [h["_source"] for h in speakers],
            "entities": self.search_entities(
                conference_id, prefix, ["topic", "technology", "project"], size
            ),
        }


def _hl(hit: dict[str, Any]) -> list[str]:
    hl = hit.get("highlight", {})
    return [*hl.get("description", []), *([] if "description" in hl else hl.get("title", []))]


def _facets(hits: list[Hit]) -> dict[str, list[tuple[str, int]]]:
    """Facet counts computed over the full ranked result window (not just the current page)."""
    counters: dict[str, Counter[str]] = {
        k: Counter()
        for k in ("track", "format", "day", "audience_level", "topic", "technology", "project")
    }
    for h in hits:
        d = h.doc
        if d.get("track"):
            counters["track"][d["track"]] += 1
        counters["format"][d["format"]] += 1
        if d.get("time"):
            counters["day"][d["time"]["day"]] += 1
        if d.get("audience_level"):
            counters["audience_level"][d["audience_level"]] += 1
        for e in d.get("entities", []):
            if e["type"] in counters:
                counters[e["type"]][e["name"]] += 1
    return {k: c.most_common(12) for k, c in counters.items()}
