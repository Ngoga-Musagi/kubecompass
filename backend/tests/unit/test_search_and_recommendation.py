from __future__ import annotations

from app.recommendation.explain import explain
from app.recommendation.profile import InterestProfile, ProfileInterest, RuleBasedIntentParser
from app.recommendation.scoring import Candidate, Components, format_fit, rescale_cosine
from app.recommendation.service import matches_filters
from app.search.filters import SessionFilters, session_filter_clauses
from app.search.fusion import rrf
from app.search.service import bm25_session_query

DEMO_INTENT = (
    "I am building an AI-powered Kubernetes autoscaler. I want to understand production AI "
    "infrastructure, GPU scheduling, inference optimization, observability, agentic systems, and "
    "workload orchestration. I prefer advanced technical talks, demonstrations, and sessions with "
    "practical engineering insights."
)


def test_rrf_rewards_agreement():
    scores = rrf([["a", "b", "c"], ["b", "a", "d"]], k=60)
    assert scores["a"] == scores["b"] > scores["c"] > 0
    assert scores["d"] < scores["a"]


def test_filters_applied_to_every_retriever():
    f = SessionFilters(
        days=["2026-11-10"], formats=["talk"], entity_ids=["topic:x"], exclude_ids=["s1"]
    )
    flt, must_not = session_filter_clauses("conf", f)
    assert {"terms": {"day": ["2026-11-10"]}} in flt
    assert {"term": {"is_content": True}} in flt
    assert {"term": {"entity_ids": "topic:x"}} in flt
    assert must_not == [{"ids": {"values": ["s1"]}}]


def test_quoted_phrase_becomes_mandatory():
    q = bm25_session_query('"model serving" latency')
    assert q["bool"]["must"][0]["multi_match"]["query"] == "model serving"
    assert q["bool"]["should"]


def test_graph_candidates_respect_filters():
    doc = {
        "id": "s",
        "is_content": True,
        "format": "demo",
        "track": "X",
        "time": {"day": "2026-11-11"},
        "entities": [{"id": "topic:a"}],
    }
    assert matches_filters(doc, SessionFilters(days=["2026-11-11"]))
    assert not matches_filters(doc, SessionFilters(days=["2026-11-10"]))
    assert not matches_filters(doc, SessionFilters(formats=["talk"]))
    assert not matches_filters(doc, SessionFilters(entity_ids=["topic:b"]))


def test_rule_parser_on_demo_persona(vocabulary):
    available = set(vocabulary.entries)
    p = RuleBasedIntentParser(vocabulary, available).parse(DEMO_INTENT)
    labels = {i.label for i in p.primary_interests}
    assert {
        "Autoscaling",
        "GPU Scheduling & Sharing",
        "AI Inference",
        "Agentic AI",
        "Observability",
        "AI Infrastructure",
    } <= labels
    assert p.experience_level == "advanced"
    assert "demo" in p.preferred_formats and "talk" in p.preferred_formats
    assert any("autoscaler" in g for g in p.learning_goals)
    assert p.parser == "rules"


def test_rule_parser_exclusions_and_unavailable_entities(vocabulary):
    available = {"topic:observability", "topic:security"}
    p = RuleBasedIntentParser(vocabulary, available).parse(
        "I like observability. Not interested in security. Also vLLM."
    )
    assert [i.entity_id for i in p.primary_interests] == ["topic:observability"]  # vLLM absent
    assert [i.entity_id for i in p.excluded_topics] == ["topic:security"]
    assert "topic:security" not in p.entity_weights()


def test_cosine_rescale_and_format_fit():
    assert rescale_cosine(0.5, 0.6, 0.85) == 0.0
    assert rescale_cosine(0.9, 0.6, 0.85) == 1.0
    assert format_fit({"format": "demo", "audience_level": "Advanced"}, ["demo"], "advanced") == 1.0
    assert format_fit({"format": "talk"}, ["demo"], "any") < 0.5


def test_explanations_are_grounded_in_the_record():
    description = (
        "Operators struggle with idle GPUs. In this talk you'll learn how to share GPUs "
        "safely with DRA. We also benchmark three schedulers."
    )
    doc = {
        "id": "s",
        "title": "GPU sharing",
        "track": "AI",
        "format": "talk",
        "audience_level": "Advanced",
        "description": description,
        "entities": [
            {
                "id": "technology:gpu",
                "name": "GPUs",
                "type": "technology",
                "origin": "extracted",
                "evidence": "share GPUs safely with DRA",
            }
        ],
    }
    profile = InterestProfile(
        primary_interests=[ProfileInterest(label="GPUs", entity_id="technology:gpu")],
        learning_goals=["share GPUs"],
        experience_level="advanced",
    )
    c = Candidate(
        session_id="s",
        doc=doc,
        bm25_rank=2,
        components=Components(learning_goal=0.9),
        highlights=["<mark>GPU</mark>"],
    )
    e = explain(c, profile)
    assert e.match_type == "direct"
    assert all(q in description for q in e.learn)  # quotes are verbatim
    assert e.learn and "you'll learn" in e.learn[0]
    assert [m.name for m in e.matched_entities] == ["GPUs"]
    assert e.supported_goals == ["share GPUs"]


def test_explore_tier_explanation_is_exploratory():
    doc = {
        "id": "s",
        "title": "KEDA",
        "format": "talk",
        "description": None,
        "entities": [
            {"id": "project:keda", "name": "KEDA", "type": "project", "origin": "extracted"},
            {
                "id": "topic:autoscaling",
                "name": "Autoscaling",
                "type": "topic",
                "origin": "extracted",
            },
        ],
    }
    profile = InterestProfile(
        primary_interests=[ProfileInterest(label="Autoscaling", entity_id="topic:autoscaling")]
    )
    e = explain(Candidate(session_id="s", doc=doc), profile, tier="explore")
    assert e.match_type == "exploratory"
    assert "KEDA" in e.summary and "Autoscaling" in e.summary
