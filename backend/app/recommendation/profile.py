"""Attendee interest profile and intent understanding.

Two parsers share one output contract:
- RuleBasedIntentParser: deterministic, vocabulary-grounded, always available.
- LLMIntentParser: richer phrasing understanding; its output is *validated
  against known entity ids*, so it cannot invent topics that are not in the data.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.infrastructure.llm import LLMProvider, LLMUnavailableError
from app.knowledge_graph.extractor import match_text
from app.knowledge_graph.vocabulary import Vocabulary
from app.normalization.text import sentences

log = logging.getLogger(__name__)

ExperienceLevel = Literal["beginner", "intermediate", "advanced", "any"]
KNOWN_FORMATS = [
    "talk",
    "keynote",
    "lightning_talk",
    "tutorial",
    "demo",
    "panel",
    "workshop",
    "contribfest",
    "poster",
    "birds_of_a_feather",
    "co_located",
    "community",
]


class ProfileInterest(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    entity_id: str | None = None  # linked knowledge-graph entity when known
    type: str | None = None


class InterestProfile(BaseModel):
    primary_interests: list[ProfileInterest] = Field(default_factory=list, max_length=20)
    secondary_interests: list[ProfileInterest] = Field(default_factory=list, max_length=30)
    learning_goals: list[str] = Field(default_factory=list, max_length=10)
    preferred_formats: list[str] = Field(default_factory=list, max_length=12)
    experience_level: ExperienceLevel = "any"
    preferred_topics: list[ProfileInterest] = Field(default_factory=list, max_length=30)
    preferred_technologies: list[ProfileInterest] = Field(default_factory=list, max_length=30)
    excluded_topics: list[ProfileInterest] = Field(default_factory=list, max_length=20)
    intent_text: str | None = Field(default=None, max_length=2000)
    parser: Literal["rules", "llm", "manual"] = "manual"

    @field_validator("learning_goals")
    @classmethod
    def _trim_goals(cls, v: list[str]) -> list[str]:
        return [g.strip()[:300] for g in v if g.strip()]

    @field_validator("preferred_formats")
    @classmethod
    def _known_formats(cls, v: list[str]) -> list[str]:
        return [f for f in v if f in KNOWN_FORMATS]

    def entity_weights(self) -> dict[str, float]:
        w: dict[str, float] = {}
        for items, weight in (
            (self.primary_interests, 1.0),
            (self.preferred_topics, 0.8),
            (self.preferred_technologies, 0.9),
            (self.secondary_interests, 0.5),
        ):
            for i in items:
                if i.entity_id:
                    w[i.entity_id] = max(w.get(i.entity_id, 0.0), weight)
        for i in self.excluded_topics:
            if i.entity_id:
                w.pop(i.entity_id, None)
        return w

    def is_empty(self) -> bool:
        return not (
            self.primary_interests
            or self.secondary_interests
            or self.learning_goals
            or self.preferred_topics
            or self.preferred_technologies
            or self.intent_text
        )

    def query_text(self) -> str:
        labels = [
            i.label
            for i in [*self.primary_interests, *self.preferred_technologies, *self.preferred_topics]
        ]
        return " ".join(dict.fromkeys(labels)) or (self.intent_text or "")

    def semantic_text(self) -> str:
        if self.intent_text:
            return self.intent_text
        parts = [i.label for i in self.primary_interests] + self.learning_goals
        return ". ".join(parts)


_GOAL_CUES = re.compile(
    r"\b(want to|wanna|would like to|looking to|hoping to|need to|trying to|learn|understand|"
    r"building|build|explore|improve|figure out|get better at|interested in|goal)\b",
    re.IGNORECASE,
)
_EXCLUDE = re.compile(
    r"(?:not interested in|no interest in|avoid|skip|exclude|except|don't care about|"
    r"do not care about|not into)\s+([^.;]+)",
    re.IGNORECASE,
)
_FORMAT_CUES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bdemos?\b|\bdemonstrations?\b", re.I), "demo"),
    (re.compile(r"\bhands[- ]on\b|\btutorials?\b", re.I), "tutorial"),
    (re.compile(r"\bworkshops?\b", re.I), "workshop"),
    (re.compile(r"\blightning\b", re.I), "lightning_talk"),
    (re.compile(r"\bpanels?\b", re.I), "panel"),
    (re.compile(r"\bkeynotes?\b", re.I), "keynote"),
    (re.compile(r"\b(technical )?talks\b|\bdeep[- ]dives?\b", re.I), "talk"),
    (re.compile(r"\bposters?\b", re.I), "poster"),
    (re.compile(r"\bcontribfest\b|\bcontribut(e|ing) code\b", re.I), "contribfest"),
]
_LEVEL_CUES: list[tuple[re.Pattern[str], ExperienceLevel]] = [
    (
        re.compile(r"\b(advanced|expert|deep[- ]dive|in-depth|senior|production[- ]grade)\b", re.I),
        "advanced",
    ),
    (
        re.compile(
            r"\b(beginner|new to|getting started|introduct|intro\b|basics|novice|first time)", re.I
        ),
        "beginner",
    ),
    (re.compile(r"\bintermediate\b", re.I), "intermediate"),
]


class RuleBasedIntentParser:
    def __init__(self, vocab: Vocabulary, available_entities: set[str]) -> None:
        self.vocab = vocab
        self.available = available_entities  # only entities present in this conference

    def parse(self, text: str) -> InterestProfile:
        text = text.strip()
        excluded_ids: set[str] = set()
        excluded: list[ProfileInterest] = []
        for clause in _EXCLUDE.findall(text):
            for m in match_text(self.vocab, clause, None):
                if m.entry.key in self.available and m.entry.key not in excluded_ids:
                    excluded_ids.add(m.entry.key)
                    excluded.append(
                        ProfileInterest(
                            label=m.entry.name, entity_id=m.entry.key, type=m.entry.type.value
                        )
                    )
        positive_text = _EXCLUDE.sub(" ", text)
        matches = [
            m
            for m in match_text(self.vocab, positive_text, None)
            if m.entry.key in self.available and m.entry.key not in excluded_ids
        ]

        # Order by first appearance so the attendee's own emphasis is preserved.
        def first_pos(m) -> int:  # type: ignore[no-untyped-def]
            spans = [
                x.start()
                for p in (m.entry.pattern, m.entry.cs_pattern)
                if p
                for x in p.finditer(positive_text)
            ]
            return min(spans) if spans else 10**6

        matches.sort(key=first_pos)
        primary = [
            ProfileInterest(label=m.entry.name, entity_id=m.entry.key, type=m.entry.type.value)
            for m in matches
        ]
        primary_ids = {p.entity_id for p in primary}
        secondary: list[ProfileInterest] = []
        for m in matches:
            for parent_slug in m.entry.parents:
                parent = self.vocab.by_slug[parent_slug]
                if (
                    parent.key in self.available
                    and parent.key not in primary_ids
                    and parent.key not in excluded_ids
                    and all(s.entity_id != parent.key for s in secondary)
                ):
                    secondary.append(
                        ProfileInterest(
                            label=parent.name, entity_id=parent.key, type=parent.type.value
                        )
                    )
        goals = [s.rstrip(".") for s in sentences(positive_text) if _GOAL_CUES.search(s)]
        formats = list(dict.fromkeys(f for pat, f in _FORMAT_CUES if pat.search(text)))
        level: ExperienceLevel = "any"
        for pat, lvl in _LEVEL_CUES:
            if pat.search(text):
                level = lvl
                break
        return InterestProfile(
            primary_interests=primary[:12],
            secondary_interests=secondary[:12],
            learning_goals=goals[:6],
            preferred_formats=formats,
            experience_level=level,
            preferred_topics=[p for p in primary if p.type == "topic"],
            preferred_technologies=[p for p in primary if p.type in ("technology", "project")],
            excluded_topics=excluded,
            intent_text=text[:2000],
            parser="rules",
        )


class _LLMProfile(BaseModel):
    primary_interests: list[str]
    secondary_interests: list[str]
    learning_goals: list[str]
    preferred_formats: list[str]
    experience_level: ExperienceLevel
    excluded_topics: list[str]


class LLMIntentParser:
    """Uses the LLM to read intent, then grounds every interest in the conference vocabulary."""

    def __init__(
        self, llm: LLMProvider, fallback: RuleBasedIntentParser, catalog: dict[str, str]
    ) -> None:
        self.llm = llm
        self.fallback = fallback
        self.catalog = catalog  # entity name -> id, only entities present in this conference

    def parse(self, text: str) -> InterestProfile:
        rules = self.fallback.parse(text)
        if not self.llm.available:
            return rules
        names = sorted(self.catalog)
        system = (
            "You convert a conference attendee's description of what they want to learn into a "
            "structured interest profile. Choose interests ONLY from the provided catalog of "
            "topics, technologies and projects that exist at this conference; copy names exactly. "
            "Primary interests are what the attendee explicitly asks for; secondary interests are "
            "closely related catalog entries that would broaden their learning. Learning goals are "
            "short paraphrases of what they want to achieve. Allowed formats: "
            + ", ".join(KNOWN_FORMATS)
            + "."
        )
        user = f"Catalog:\n{'; '.join(names)}\n\nAttendee description:\n{text}"
        try:
            out = self.llm.structured(system, user, _LLMProfile)
        except LLMUnavailableError as exc:
            log.info("LLM intent parsing unavailable (%s); using rules", exc)
            return rules

        def ground(labels: list[str]) -> list[ProfileInterest]:
            out_items: list[ProfileInterest] = []
            lookup = {n.lower(): (n, i) for n, i in self.catalog.items()}
            for label in labels:
                hit = lookup.get(label.strip().lower())
                if hit and all(x.entity_id != hit[1] for x in out_items):
                    out_items.append(
                        ProfileInterest(
                            label=hit[0], entity_id=hit[1], type=hit[1].split(":", 1)[0]
                        )
                    )
            return out_items

        # Merge policy: the rule parser is grounded in the literal text, so its findings are a
        # floor the LLM can add to but not remove; explicit constraints (exclusions, level,
        # formats) come from the rules whenever the text stated them, since small local models
        # tend to over-generalize them (e.g. "not security" -> every security-adjacent topic).
        excluded = rules.excluded_topics or ground(out.excluded_topics)
        excluded_ids = {e.entity_id for e in excluded}
        primary = [p for p in ground(out.primary_interests) if p.entity_id not in excluded_ids]
        primary += [
            r for r in rules.primary_interests if all(p.entity_id != r.entity_id for p in primary)
        ]
        secondary = [
            s
            for s in ground(out.secondary_interests)
            if all(p.entity_id != s.entity_id for p in primary) and s.entity_id not in excluded_ids
        ]
        return InterestProfile(
            primary_interests=primary[:12],
            secondary_interests=secondary[:12] or rules.secondary_interests,
            learning_goals=[g for g in out.learning_goals if g.strip()][:6] or rules.learning_goals,
            preferred_formats=rules.preferred_formats or out.preferred_formats,
            experience_level=(
                rules.experience_level if rules.experience_level != "any" else out.experience_level
            ),
            preferred_topics=[p for p in primary if p.type == "topic"],
            preferred_technologies=[p for p in primary if p.type in ("technology", "project")],
            excluded_topics=excluded,
            intent_text=text[:2000],
            parser="llm",
        )
