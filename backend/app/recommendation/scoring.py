"""Explainable, configurable recommendation scoring. All components are in [0, 1]."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from app.config.settings import get_settings


class Weights(BaseModel):
    interest_match: float
    topic_technology: float
    graph_relevance: float
    learning_goal: float
    novelty: float
    format_preference: float

    def normalized(self) -> Weights:
        total = sum(self.model_dump().values()) or 1.0
        return Weights(**{k: v / total for k, v in self.model_dump().items()})


class Tiers(BaseModel):
    must_attend_ratio: float
    highly_relevant_ratio: float
    min_top_score: float
    must_attend_max: int
    highly_relevant_max: int
    explore_max: int
    explore_min_novelty: float


class RetrievalCfg(BaseModel):
    window: int
    graph_candidates: int


class RankingConfig(BaseModel):
    weights: Weights
    tiers: Tiers
    retrieval: RetrievalCfg


@lru_cache
def load_ranking_config(path: Path | None = None) -> RankingConfig:
    path = path or get_settings().ranking_path
    return RankingConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def rescale_cosine(cos: float | None, floor: float, ceiling: float) -> float:
    if cos is None:
        return 0.0
    return max(0.0, min(1.0, (cos - floor) / (ceiling - floor)))


LEVEL_FIT = {
    "advanced": {"Advanced": 1.0, "Any Level": 0.6, "Beginner": 0.15},
    "intermediate": {"Advanced": 0.7, "Any Level": 0.9, "Beginner": 0.5},
    "beginner": {"Advanced": 0.2, "Any Level": 0.8, "Beginner": 1.0},
}


@dataclass
class Components:
    interest_match: float = 0.0
    topic_technology: float = 0.0
    graph_relevance: float = 0.0
    learning_goal: float = 0.0
    novelty: float = 0.0
    format_preference: float = 0.5

    def total(self, w: Weights) -> float:
        return sum(getattr(self, k) * v for k, v in w.model_dump().items())

    def as_dict(self) -> dict[str, float]:
        return {k: round(v, 4) for k, v in self.__dict__.items()}


@dataclass
class Candidate:
    session_id: str
    doc: dict[str, Any]
    bm25_rank: int | None = None
    bm25_score: float | None = None
    vector_rank: int | None = None
    intent_similarity: float | None = None
    goal_similarity: float | None = None
    graph_score: float = 0.0
    from_graph_only: bool = False
    highlights: list[str] = field(default_factory=list)
    matched_entities: list[dict[str, Any]] = field(default_factory=list)
    components: Components = field(default_factory=Components)
    score: float = 0.0


def format_fit(doc: dict[str, Any], preferred_formats: list[str], experience: str) -> float:
    fmt_score = 0.5
    if preferred_formats:
        fmt_score = 1.0 if doc.get("format") in preferred_formats else 0.2
    level = doc.get("audience_level")
    if experience in LEVEL_FIT and level:
        return 0.5 * fmt_score + 0.5 * LEVEL_FIT[experience].get(level, 0.5)
    return fmt_score
