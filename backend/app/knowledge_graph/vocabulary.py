"""Curated vocabulary loading and compiled matchers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from app.config.settings import get_settings
from app.domain.models import EntityType

_SECTION_TYPES = {
    "topics": EntityType.TOPIC,
    "technologies": EntityType.TECHNOLOGY,
    "projects": EntityType.PROJECT,
}


@dataclass
class VocabularyEntry:
    key: str  # canonical entity id, e.g. "project:vllm"
    slug: str
    name: str
    type: EntityType
    aliases: list[str]
    cs_aliases: list[str]
    parents: list[str]  # slugs
    source_tags: list[str]
    pattern: re.Pattern[str] | None = field(default=None, repr=False)
    cs_pattern: re.Pattern[str] | None = field(default=None, repr=False)


def _compile(aliases: list[str], flags: int) -> re.Pattern[str] | None:
    if not aliases:
        return None
    alts = sorted({re.escape(a) for a in aliases}, key=len, reverse=True)
    # Word-ish boundaries that also treat '-' and '.' inside names (llm-d, Metal3.io) correctly.
    return re.compile(r"(?<![\w-])(?:" + "|".join(alts) + r")(?![\w-])", flags)


@dataclass
class Vocabulary:
    version: str
    entries: dict[str, VocabularyEntry]  # by key
    by_slug: dict[str, VocabularyEntry]
    by_source_tag: dict[str, VocabularyEntry]
    strict_match: frozenset[str] = frozenset()  # slugs needing stronger evidence
    low_signal: frozenset[str] = frozenset()  # entity keys damped in ranking/similarity

    def get(self, slug: str) -> VocabularyEntry | None:
        return self.by_slug.get(slug)


def entity_key(etype: EntityType, slug: str) -> str:
    return f"{etype.value}:{slug}"


def load_vocabulary(path: Path) -> Vocabulary:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries: dict[str, VocabularyEntry] = {}
    by_slug: dict[str, VocabularyEntry] = {}
    by_tag: dict[str, VocabularyEntry] = {}
    for section, etype in _SECTION_TYPES.items():
        for item in raw.get(section, []):
            slug = item["id"]
            if slug in by_slug:
                raise ValueError(f"Duplicate vocabulary id: {slug}")
            entry = VocabularyEntry(
                key=entity_key(etype, slug),
                slug=slug,
                name=item["name"],
                type=etype,
                aliases=list(item.get("aliases", [])),
                cs_aliases=list(item.get("cs_aliases", [])),
                parents=list(item.get("parents", [])),
                source_tags=list(item.get("source_tags", [])),
            )
            entry.pattern = _compile(entry.aliases, re.IGNORECASE)
            entry.cs_pattern = _compile(entry.cs_aliases, 0)
            entries[entry.key] = entry
            by_slug[slug] = entry
            for tag in entry.source_tags:
                by_tag[tag.lower()] = entry
    for e in entries.values():
        unknown = [p for p in e.parents if p not in by_slug]
        if unknown:
            raise ValueError(f"Vocabulary entry {e.slug} has unknown parents {unknown}")
    return Vocabulary(
        version=str(raw.get("version")),
        entries=entries,
        by_slug=by_slug,
        by_source_tag=by_tag,
        strict_match=frozenset(raw.get("strict_match", [])),
        low_signal=frozenset(raw.get("low_signal", [])),
    )


@lru_cache
def get_vocabulary() -> Vocabulary:
    return load_vocabulary(get_settings().vocabulary_path)
