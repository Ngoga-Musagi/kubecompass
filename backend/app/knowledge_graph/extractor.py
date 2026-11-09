"""Dictionary-based entity extraction with evidence.

Every match records the sentence it was found in so the UI can show *why* a
session is linked to a technology. Matches are `Origin.EXTRACTED`, never
`EXPLICIT`; explicit source tags are handled separately with `Origin.EXPLICIT`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.models import EntityRef, Origin
from app.knowledge_graph.vocabulary import Vocabulary, VocabularyEntry
from app.normalization.text import sentences

_MAX_EVIDENCE = 240


@dataclass
class Match:
    entry: VocabularyEntry
    in_title: bool
    mentions: int
    evidence: str


def _find(entry: VocabularyEntry, text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for pat in (entry.pattern, entry.cs_pattern):
        if pat is not None:
            spans.extend(m.span() for m in pat.finditer(text))
    return spans


def _evidence_sentence(text: str, start: int) -> str:
    # Find the sentence containing the match start.
    pos = 0
    for sent in sentences(text):
        idx = text.find(sent, pos)
        if idx == -1:
            continue
        if idx <= start < idx + len(sent):
            return sent if len(sent) <= _MAX_EVIDENCE else sent[: _MAX_EVIDENCE - 1] + "…"
        pos = idx
    lo = max(0, start - 100)
    return text[lo : lo + _MAX_EVIDENCE].strip()


def match_text(vocab: Vocabulary, title: str, body: str | None) -> list[Match]:
    matches: list[Match] = []
    body = body or ""
    for entry in vocab.entries.values():
        t_spans = _find(entry, title)
        b_spans = _find(entry, body)
        if not t_spans and not b_spans:
            continue
        mentions = len(t_spans) + len(b_spans)
        if entry.slug in vocab.strict_match and not t_spans and mentions < 2:
            continue
        evidence = f"Title: {title}" if t_spans else _evidence_sentence(body, b_spans[0][0])
        matches.append(Match(entry, bool(t_spans), mentions, evidence))
    return matches


def confidence(m: Match) -> float:
    if m.in_title:
        return 0.95
    if m.mentions >= 3:
        return 0.9
    if m.mentions == 2:
        return 0.8
    return 0.65


def to_refs(matches: list[Match]) -> list[EntityRef]:
    return [
        EntityRef(
            id=m.entry.key,
            name=m.entry.name,
            type=m.entry.type,
            origin=Origin.EXTRACTED,
            confidence=confidence(m),
            evidence=m.evidence,
        )
        for m in sorted(matches, key=lambda m: (-confidence(m), m.entry.name))
    ]
