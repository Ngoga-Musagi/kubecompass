from __future__ import annotations

from datetime import UTC, datetime

import networkx as nx

from app.domain.models import Origin, RelationType
from app.ingestion.sessionize.adapter import SessionizeAdapter
from app.knowledge_graph.builder import KnowledgeGraphBuilder
from app.knowledge_graph.extractor import match_text
from app.knowledge_graph.store import NetworkXGraphStore
from tests.conftest import make_payload, session_raw


def _build(conference, vocabulary, sessions, speakers=None):
    p = make_payload(sessions, speakers or [])
    out = SessionizeAdapter(min_sessions=1).normalize(p, conference, datetime.now(UTC), "v")
    b = KnowledgeGraphBuilder(vocabulary, conference.id, conference.non_organization_values)
    return out, b.build(out.sessions, out.speakers, None)


def test_extraction_keeps_evidence_sentence(vocabulary):
    body = "We run vLLM behind KServe. Another sentence about cooking."
    matches = {m.entry.slug: m for m in match_text(vocabulary, "Serving at scale", body)}
    assert "vllm" in matches and "kserve" in matches
    assert matches["vllm"].evidence == "We run vLLM behind KServe."


def test_case_sensitive_acronyms_do_not_match_common_words(vocabulary):
    slugs = {m.entry.slug for m in match_text(vocabulary, "", "We ray-trace and go fishing.")}
    assert "ray" not in slugs and "golang" not in slugs


def test_generic_topic_needs_stronger_evidence(vocabulary):
    once = {m.entry.slug for m in match_text(vocabulary, "", "It is secure.")}
    assert "security" not in once
    titled = {m.entry.slug for m in match_text(vocabulary, "Security at scale", None)}
    assert "security" in titled


def test_explicit_tags_vs_extracted_text_origins(conference, vocabulary):
    sessions = [
        session_raw(
            "1",
            "Tracing everything",
            cats=[10, 30, 31],
            description="We use Prometheus for metrics and Prometheus alerts.",
        )
    ]
    _, g = _build(conference, vocabulary, sessions)
    rels = {(r.target_id, r.origin) for r in g.relationships if r.source_id.endswith(":1")}
    assert ("project:opentelemetry", Origin.EXPLICIT) in rels  # from CNCF Projects tag
    assert ("project:brand-new-proj", Origin.EXPLICIT) in rels  # unknown tag kept as explicit
    assert ("project:prometheus", Origin.EXTRACTED) in rels  # from abstract text


def test_every_relationship_has_method_and_non_explicit_ones_have_evidence(conference, vocabulary):
    sessions = [
        session_raw("1", "GPU sharing with HAMi", description="HAMi shares GPUs.", speakers=["s1"])
    ]
    speakers = [
        {
            "id": "s1",
            "fullName": "Ann Bee",
            "sessions": [1],
            "bio": "Ann is a maintainer of Volcano.",
            "questionAnswers": [{"questionId": 128829, "answerValue": "Maintainer"}],
        }
    ]
    _, g = _build(conference, vocabulary, sessions, speakers)
    assert all(r.method for r in g.relationships)
    assert all(r.evidence for r in g.relationships if r.origin != Origin.EXPLICIT)
    works_on = [r for r in g.relationships if r.type == RelationType.WORKS_ON]
    assert works_on and works_on[0].origin == Origin.EXTRACTED
    # "Maintainer" typed into the Company field is not an organization.
    assert not any(e.id.startswith("organization:") for e in g.entities)


def test_curated_hierarchy_marked_curated(conference, vocabulary):
    _, g = _build(conference, vocabulary, [session_raw("1", "Serving with vLLM")])
    part_of = [r for r in g.relationships if r.type == RelationType.PART_OF]
    assert part_of and all(r.origin == Origin.CURATED for r in part_of)


def test_no_duplicate_relationship_ids(conference, vocabulary):
    sessions = [
        session_raw(
            str(i),
            f"vLLM and KServe {i}",
            start=f"2026-11-10T{10 + i}:00:00",
            end=f"2026-11-10T{10 + i}:30:00",
        )
        for i in range(4)
    ]
    _, g = _build(conference, vocabulary, sessions)
    ids = [r.id for r in g.relationships]
    assert len(ids) == len(set(ids))


def test_cooccurrence_creates_inferred_edges(conference, vocabulary):
    sessions = [
        session_raw(
            str(i),
            f"vLLM on KServe part {i}",
            start=f"2026-11-10T{10 + i}:00:00",
            end=f"2026-11-10T{10 + i}:30:00",
        )
        for i in range(4)
    ]
    # Background corpus so co-occurrence has meaningful lift (requires lift >= 1.5).
    sessions += [
        session_raw(
            f"9{i}",
            f"Helm chart talk {i}",
            start=f"2026-11-11T{10 + i}:00:00",
            end=f"2026-11-11T{10 + i}:30:00",
        )
        for i in range(6)
    ]
    _, g = _build(conference, vocabulary, sessions)
    co = [r for r in g.relationships if r.method == "co_occurrence"]
    assert co and all(r.origin == Origin.INFERRED and "Co-occur in" in r.evidence for r in co)


def test_personalized_pagerank_prefers_connected_nodes():
    g = nx.MultiDiGraph()
    g.add_edge("topic:a", "s1", id="1", type="COVERS", confidence=1.0, weight=1.0)
    g.add_edge("topic:a", "s2", id="2", type="COVERS", confidence=1.0, weight=1.0)
    g.add_edge("topic:b", "s3", id="3", type="COVERS", confidence=1.0, weight=1.0)
    store = NetworkXGraphStore(g)
    pr = store.personalized_pagerank({"topic:a": 1.0})
    assert pr["s1"] > pr.get("s3", 0)
    assert store.shortest_path("s1", "s2") == ["s1", "topic:a", "s2"]
    assert store.shortest_path("s1", "s3") is None
