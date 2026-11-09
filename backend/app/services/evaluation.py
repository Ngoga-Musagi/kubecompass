"""Search & recommendation evaluation over a judged query set (data/evaluation/).

Compares: BM25, vector, hybrid (app RRF), hybrid (native ES RRF), hybrid + graph
expansion, and the full personalized pipeline. Metrics: Precision@5, Recall@10,
nDCG@10 (graded), mean latency and explanation coverage.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config.settings import get_settings
from app.knowledge_graph.extractor import match_text
from app.knowledge_graph.store import ConferenceReadModel
from app.recommendation.profile import RuleBasedIntentParser
from app.services.container import Container, get_container

K_P, K_R, K_N = 5, 10, 10


def precision_at(ranked: list[str], rel: dict[str, int], k: int) -> float:
    return sum(1 for d in ranked[:k] if rel.get(d, 0) > 0) / k


def recall_at(ranked: list[str], rel: dict[str, int], k: int) -> float:
    relevant = {d for d, g in rel.items() if g > 0}
    return len(relevant & set(ranked[:k])) / len(relevant) if relevant else 0.0


def ndcg_at(ranked: list[str], rel: dict[str, int], k: int) -> float:
    dcg = sum((2 ** rel.get(d, 0) - 1) / math.log2(i + 2) for i, d in enumerate(ranked[:k]))
    ideal = sorted((g for g in rel.values() if g > 0), reverse=True)[:k]
    idcg = sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def _dedupe_by_title(ids: list[str], rm: ConferenceReadModel) -> list[str]:
    """Recurring sessions share a title; judge them once (first occurrence wins)."""
    seen: set[str] = set()
    out = []
    for i in ids:
        t = rm.sessions[i]["title"].strip().lower() if i in rm.sessions else i
        if t not in seen:
            seen.add(t)
            out.append(i)
    return out


def build_runners(
    c: Container, rm: ConferenceReadModel
) -> dict[str, Callable[[str], tuple[list[str], float]]]:
    cid = rm.conference_id
    parser = RuleBasedIntentParser(c.vocabulary, set(rm.entities))

    def search(mode: str) -> Callable[[str], tuple[list[str], float]]:
        def run(q: str) -> tuple[list[str], float]:
            r = c.search.search_sessions(cid, q, mode=mode, size=20)  # type: ignore[arg-type]
            return [h.id for h in r.hits], 0.0

        return run

    def hybrid_graph(q: str) -> tuple[list[str], float]:
        """Hybrid results re-ranked with personalized PageRank from entities named in q."""
        r = c.search.search_sessions(cid, q, mode="hybrid", size=40)
        seeds = {
            m.entry.key: 1.0
            for m in match_text(c.vocabulary, q, None)
            if m.entry.key in rm.entities
        }
        ppr = rm.graph.personalized_pagerank(seeds) if seeds else {}
        top = max((ppr.get(h.id, 0) for h in r.hits), default=0) or 1
        rrf_top = r.hits[0].score if r.hits else 1
        scored = [(0.7 * h.score / rrf_top + 0.3 * ppr.get(h.id, 0) / top, h.id) for h in r.hits]
        extra = sorted(
            (
                (v, k)
                for k, v in ppr.items()
                if k in rm.sessions
                and rm.sessions[k].get("is_content", True)
                and k not in {h.id for h in r.hits}
            ),
            reverse=True,
        )[:10]
        scored += [(0.3 * v / top, k) for v, k in extra]
        return [k for _, k in sorted(scored, reverse=True)], 0.0

    def personalized(q: str) -> tuple[list[str], float]:
        profile = parser.parse(q)
        res = c.recommendations.recommend(rm, profile)
        recs = [*res.must_attend, *res.highly_relevant, *res.explore]
        recs.sort(key=lambda x: -x.score)
        covered = sum(
            1
            for x in recs[:10]
            if x.explanation.matched_entities
            or x.explanation.learn
            or x.explanation.evidence_snippets
        )
        return [x.session.id for x in recs], covered / max(1, min(10, len(recs)))

    return {
        "bm25": search("keyword"),
        "vector": search("vector"),
        "hybrid_rrf_app": search("hybrid"),
        "hybrid_rrf_native": search("hybrid_native"),
        "hybrid_plus_graph": hybrid_graph,
        "personalized_pipeline": personalized,
    }


def run_evaluation(
    conference_id: str, dataset: str | None = None, output: str | None = None
) -> dict[str, Any]:
    settings = get_settings()
    path = Path(dataset) if dataset else settings.data_dir / "evaluation" / "queries.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    c = get_container()
    rm = c.read_models.get(conference_id)
    if rm is None:
        raise RuntimeError("Conference not indexed; run `kubecompass ingest` first")
    runners = build_runners(c, rm)
    per_method: dict[str, dict[str, list[float]]] = {
        m: {"p5": [], "r10": [], "ndcg10": [], "latency_ms": [], "explained": []} for m in runners
    }
    per_query: list[dict[str, Any]] = []
    for item in spec["queries"]:
        rel = {k: int(v) for k, v in item["judgments"].items()}
        row: dict[str, Any] = {"id": item["id"], "query": item["query"]}
        for name, run in runners.items():
            run(item["query"])  # warm caches (embedding, ES) so latency is comparable
            t0 = time.perf_counter()
            ranked, explained = run(item["query"])
            ms = (time.perf_counter() - t0) * 1000
            ranked = _dedupe_by_title(ranked, rm)
            m = per_method[name]
            m["p5"].append(precision_at(ranked, rel, K_P))
            m["r10"].append(recall_at(ranked, rel, K_R))
            m["ndcg10"].append(ndcg_at(ranked, rel, K_N))
            m["latency_ms"].append(ms)
            if name == "personalized_pipeline":
                m["explained"].append(explained)
            row[name] = round(m["ndcg10"][-1], 3)
        per_query.append(row)

    summary = {
        name: {
            "P@5": round(statistics.mean(v["p5"]), 3),
            "R@10": round(statistics.mean(v["r10"]), 3),
            "nDCG@10": round(statistics.mean(v["ndcg10"]), 3),
            "latency_ms_mean": round(statistics.mean(v["latency_ms"]), 1),
            **(
                {"explanation_coverage": round(statistics.mean(v["explained"]), 3)}
                if v["explained"]
                else {}
            ),
        }
        for name, v in per_method.items()
    }
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "conference_id": conference_id,
        "data_version": rm.version,
        "queries": len(spec["queries"]),
        "judgment_method": spec.get("judgment_method"),
        "summary": summary,
        "per_query_ndcg10": per_query,
    }
    out = Path(output) if output else settings.data_dir / "evaluation" / "results.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def build_pool(
    conference_id: str, queries: list[dict[str, str]], depth: int = 12
) -> list[dict[str, Any]]:
    """Union of top-`depth` results from every method, for relevance judging."""
    c = get_container()
    rm = c.read_models.get(conference_id)
    assert rm is not None
    runners = build_runners(c, rm)
    pool = []
    for q in queries:
        ids: list[str] = []
        for run in runners.values():
            ranked, _ = run(q["query"])
            for i in _dedupe_by_title(ranked, rm)[:depth]:
                if i not in ids:
                    ids.append(i)
        pool.append(
            {
                **q,
                "candidates": [
                    {
                        "id": i,
                        "title": rm.sessions[i]["title"],
                        "abstract": (rm.sessions[i].get("description") or "")[:240],
                    }
                    for i in ids
                ],
            }
        )
    return pool
