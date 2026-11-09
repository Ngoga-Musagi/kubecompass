"""Evidence-grounded recommendation explanations.

Every sentence in an explanation is either (a) a template filled with values
computed from the data, or (b) a verbatim quote from the session abstract.
No generated prose about session content or speaker expertise.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from app.normalization.text import sentences
from app.recommendation.profile import InterestProfile
from app.recommendation.scoring import Candidate

_LEARN_CUES = re.compile(
    r"\b(you('|’)ll|you will|attendees will|learn|walk away|takeaways?|we('|’)ll (show|share|cover|"
    r"demonstrate|explore|dive)|we will (show|share|cover|demonstrate|explore)|this (talk|session) "
    r"(will )?(covers?|explores?|shows?|demonstrates?)|deep dive)\b",
    re.IGNORECASE,
)


class MatchedEntity(BaseModel):
    id: str
    name: str
    type: str
    origin: str
    evidence: str | None = None
    profile_weight: float


class Explanation(BaseModel):
    match_type: str  # direct | semantic | exploratory
    summary: str
    reasons: list[str] = Field(default_factory=list)
    matched_entities: list[MatchedEntity] = Field(default_factory=list)
    supported_goals: list[str] = Field(default_factory=list)
    learn: list[str] = Field(default_factory=list)  # verbatim abstract quotes
    evidence_snippets: list[str] = Field(default_factory=list)  # ES highlights (verbatim)
    retrieval: dict[str, Any] = Field(default_factory=dict)


def _learn_quotes(description: str | None, cue_terms: list[str], limit: int = 2) -> list[str]:
    if not description:
        return []
    sents = [s for s in sentences(description) if 30 <= len(s) <= 320]
    cued = [s for s in sents if _LEARN_CUES.search(s)]
    if cued:
        return cued[:limit]
    terms = [t.lower() for t in cue_terms if t]
    scored = sorted(
        ((sum(t in s.lower() for t in terms), i, s) for i, s in enumerate(sents)),
        key=lambda x: (-x[0], x[1]),
    )
    return [s for score, _, s in scored if score > 0][:limit]


def explain(
    c: Candidate,
    profile: InterestProfile,
    *,
    tier: str = "highly_relevant",
    low_signal: frozenset[str] = frozenset(),
    goal_sim_threshold: float = 0.35,
) -> Explanation:
    weights = profile.entity_weights()
    matched = [
        MatchedEntity(
            id=e["id"],
            name=e["name"],
            type=e["type"],
            origin=e["origin"],
            evidence=e.get("evidence"),
            profile_weight=weights[e["id"]],
        )
        for e in c.doc.get("entities", [])
        if e["id"] in weights
    ]
    matched.sort(key=lambda m: (m.id in low_signal, -m.profile_weight, m.origin != "explicit"))
    primary = [m for m in matched if m.profile_weight >= 0.8 and m.id not in low_signal] or [
        m for m in matched if m.profile_weight >= 0.8
    ]
    secondary = [m for m in matched if m.profile_weight < 0.8]
    new_entities = [
        e["name"]
        for e in c.doc.get("entities", [])
        if e["id"] not in weights
        and e["id"] not in low_signal
        and e["type"] in ("technology", "project", "topic")
    ]
    comp = c.components

    reasons: list[str] = []
    if primary:
        reasons.append("Covers your interests: " + ", ".join(m.name for m in primary[:4]) + ".")
    if secondary:
        reasons.append(
            "Connects to related areas: " + ", ".join(m.name for m in secondary[:3]) + "."
        )
    if c.bm25_rank is not None and c.bm25_rank <= 10:
        reasons.append(f"Strong keyword match for your profile (rank {c.bm25_rank}).")
    if c.intent_similarity is not None and c.intent_similarity >= 0.6:
        reasons.append(
            f"Abstract is semantically close to what you described "
            f"(similarity {c.intent_similarity:.2f})."
        )
    if c.from_graph_only:
        reasons.append(
            "Found through the knowledge graph rather than direct search, "
            "via topics connected to your interests."
        )
    level = c.doc.get("audience_level")
    if profile.experience_level != "any" and level:
        reasons.append(f"Audience level: {level} (you asked for {profile.experience_level}).")
    if profile.preferred_formats and c.doc.get("format") in profile.preferred_formats:
        reasons.append(f"Matches your preferred format ({c.doc['format'].replace('_', ' ')}).")

    supported_goals: list[str] = []
    if profile.learning_goals and comp.learning_goal >= goal_sim_threshold:
        supported_goals = profile.learning_goals[:2]

    if tier == "explore" or c.from_graph_only:
        match_type = "exploratory"
    elif primary or (c.bm25_rank is not None and c.bm25_rank <= 20):
        match_type = "direct"
    else:
        match_type = "semantic"

    if match_type == "exploratory":
        bridge = primary or secondary or matched
        fresh = ", ".join(new_entities[:2])
        summary = (f"New angle: {fresh}" if fresh else "Adjacent to your interests") + (
            f", connected to your interest in {bridge[0].name}" if bridge else ""
        )
        if new_entities:
            reasons.insert(
                0, "Brings in topics outside your profile: " + ", ".join(new_entities[:4]) + "."
            )
    elif primary:
        summary = f"Directly about {', '.join(m.name for m in primary[:2])}"
    elif match_type == "direct":
        summary = "Strong match for the terms in your profile"
    else:
        summary = "Semantically related to what you want to learn"

    return Explanation(
        match_type=match_type,
        summary=summary,
        reasons=reasons,
        matched_entities=matched[:8],
        supported_goals=supported_goals,
        learn=_learn_quotes(c.doc.get("description"), [m.name for m in matched]),
        evidence_snippets=c.highlights[:2],
        retrieval={
            "bm25_rank": c.bm25_rank,
            "vector_rank": c.vector_rank,
            "intent_similarity": None
            if c.intent_similarity is None
            else round(c.intent_similarity, 3),
            "graph_score": round(c.graph_score, 4),
            "from_graph_only": c.from_graph_only,
        },
    )
