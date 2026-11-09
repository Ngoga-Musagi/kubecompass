"""Builds entities and provenance-carrying relationships from normalized records."""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations

import numpy as np

from app.domain.models import (
    Entity,
    EntityRef,
    EntityType,
    Origin,
    Relationship,
    RelationType,
    Session,
    Speaker,
)
from app.knowledge_graph.extractor import match_text, to_refs
from app.knowledge_graph.vocabulary import Vocabulary, entity_key
from app.normalization.text import slugify

_ROLE_WORDS = re.compile(
    r"\b(maintainer|maintains|maintaining|co-?maintainer|contributor|contributes|contributing|"
    r"creator|created|co-?founder|founded|author|lead|leads|chair|co-?chair|core team|committer|"
    r"steering)\b",
    re.IGNORECASE,
)
_ORG_SUFFIX = re.compile(r"[,\s]+(inc\.?|llc|ltd\.?|corp\.?|corporation|gmbh|co\.)$", re.IGNORECASE)

REL_TYPE_FOR = {
    EntityType.TOPIC: RelationType.COVERS,
    EntityType.TECHNOLOGY: RelationType.USES,
    EntityType.PROJECT: RelationType.DISCUSSES,
}


def _rel_id(cid: str, src: str, rtype: RelationType, dst: str) -> str:
    return hashlib.sha1(f"{cid}|{src}|{rtype}|{dst}".encode()).hexdigest()[:20]


def normalize_org(name: str) -> str:
    return _ORG_SUFFIX.sub("", name.strip()).strip()


@dataclass
class GraphBuildResult:
    entities: list[Entity]
    relationships: list[Relationship]
    stats: dict[str, int] = field(default_factory=dict)


class KnowledgeGraphBuilder:
    def __init__(
        self,
        vocab: Vocabulary,
        conference_id: str,
        non_organizations: list[str] | None = None,
        related_cosine_range: tuple[float, float] = (0.70, 0.90),
    ) -> None:
        # Session-similarity rescale range; model-specific (embedding-calibration.yaml).
        self.related_cosine_range = related_cosine_range
        self.vocab = vocab
        self.cid = conference_id
        self.non_orgs = {slugify(v) for v in (non_organizations or [])}
        self.entities: dict[str, Entity] = {}
        self.rels: dict[str, Relationship] = {}

    # ---- helpers -----------------------------------------------------------------------------
    def _entity(self, key: str, etype: EntityType, name: str, origin: Origin) -> Entity:
        if key not in self.entities:
            self.entities[key] = Entity(
                id=key, conference_id=self.cid, type=etype, name=name, origin=origin
            )
        return self.entities[key]

    def _vocab_entity(self, key: str) -> Entity:
        e = self.vocab.entries[key]
        return self._entity(key, e.type, e.name, Origin.CURATED)

    def _rel(
        self,
        src: str,
        src_t: EntityType,
        rtype: RelationType,
        dst: str,
        dst_t: EntityType,
        *,
        origin: Origin,
        method: str,
        confidence: float = 1.0,
        evidence: str | None = None,
        weight: float = 1.0,
    ) -> None:
        rid = _rel_id(self.cid, src, rtype, dst)
        existing = self.rels.get(rid)
        # Keep the strongest provenance when the same edge is found twice.
        rank = [
            Origin.EXPLICIT,
            Origin.VERIFIED,
            Origin.EXTRACTED,
            Origin.CURATED,
            Origin.AI_EXTRACTED,
            Origin.INFERRED,
        ]
        if existing and rank.index(existing.origin) <= rank.index(origin):
            return
        self.rels[rid] = Relationship(
            id=rid,
            conference_id=self.cid,
            source_id=src,
            source_type=src_t,
            target_id=dst,
            target_type=dst_t,
            type=rtype,
            origin=origin,
            method=method,
            confidence=round(confidence, 3),
            evidence=evidence,
            weight=weight,
        )

    # ---- build ---------------------------------------------------------------------------
    def build(
        self,
        sessions: list[Session],
        speakers: list[Speaker],
        session_vectors: np.ndarray | None = None,
    ) -> GraphBuildResult:
        speaker_by_id = {s.id: s for s in speakers}
        for s in sessions:
            self.add_session(s)
        for sp in speakers:
            self._speaker(sp)
        self._maintainer_inference(sessions, speaker_by_id)
        self._curated_hierarchy()
        self._cooccurrence(sessions)
        related = self._related_sessions(
            sessions,
            session_vectors,
            cos_floor=self.related_cosine_range[0],
            cos_ceiling=self.related_cosine_range[1],
        )
        self._counts(sessions, speakers)
        return GraphBuildResult(
            entities=list(self.entities.values()),
            relationships=list(self.rels.values()),
            stats={
                "entities": len(self.entities),
                "relationships": len(self.rels),
                "related_session_edges": related,
                **{
                    f"entities.{k}": v
                    for k, v in Counter(e.type.value for e in self.entities.values()).items()
                },
                **{
                    f"origin.{k}": v
                    for k, v in Counter(r.origin.value for r in self.rels.values()).items()
                },
            },
        )

    def add_session(self, s: Session) -> None:
        """Attach explicit + extracted entities to a session and create its edges."""
        S = EntityType.SESSION
        self._entity(s.id, S, s.title, Origin.EXPLICIT)
        refs: dict[str, EntityRef] = {}

        if s.track:
            tkey = f"track:{slugify(s.track)}"
            self._entity(tkey, EntityType.TRACK, s.track, Origin.EXPLICIT)
            self._rel(
                s.id,
                S,
                RelationType.BELONGS_TO_TRACK,
                tkey,
                EntityType.TRACK,
                origin=Origin.EXPLICIT,
                method="sessionize_category",
                evidence=f"Sessionize track: {s.track}",
            )
        if s.room:
            rkey = f"room:{s.room.id}"
            self._entity(rkey, EntityType.ROOM, s.room.name, Origin.EXPLICIT)
            self._rel(
                s.id,
                S,
                RelationType.SCHEDULED_IN,
                rkey,
                EntityType.ROOM,
                origin=Origin.EXPLICIT,
                method="sessionize_field",
                evidence=f"Sessionize room: {s.room.name}",
            )

        # Explicit tags: CNCF project category + co-located event subtopics.
        for tag, method in [
            *((t, "sessionize_project_tag") for t in s.project_tags),
            *((t, "sessionize_subtopic") for t in s.subtopics),
        ]:
            entry = self.vocab.by_source_tag.get(tag.lower())
            if entry is not None:
                self._vocab_entity(entry.key)
                key, etype, name = entry.key, entry.type, entry.name
            elif method == "sessionize_project_tag":
                key = entity_key(EntityType.PROJECT, slugify(tag))
                self._entity(key, EntityType.PROJECT, tag, Origin.EXPLICIT)
                etype, name = EntityType.PROJECT, tag
            else:
                continue  # unmapped subtopics (e.g. "BoF") are formats, not entities
            self._rel(
                s.id,
                S,
                REL_TYPE_FOR[etype],
                key,
                etype,
                origin=Origin.EXPLICIT,
                method=method,
                evidence=f"Sessionize tag: {tag}",
            )
            refs[key] = EntityRef(
                id=key,
                name=name,
                type=etype,
                origin=Origin.EXPLICIT,
                evidence=f"Tagged '{tag}' in Sessionize",
            )

        # Extracted from title + abstract.
        for ref in to_refs(match_text(self.vocab, s.title, s.description)):
            self._vocab_entity(ref.id)
            self._rel(
                s.id,
                S,
                REL_TYPE_FOR[ref.type],
                ref.id,
                ref.type,
                origin=Origin.EXTRACTED,
                method="vocabulary_match",
                confidence=ref.confidence,
                evidence=ref.evidence,
            )
            refs.setdefault(ref.id, ref)
        s.entities = sorted(
            refs.values(), key=lambda r: (r.origin != Origin.EXPLICIT, -r.confidence, r.name)
        )

    def _speaker(self, sp: Speaker) -> None:
        P = EntityType.SPEAKER
        self._entity(sp.id, P, sp.full_name, Origin.EXPLICIT)
        for sid in sp.session_ids:
            self._rel(
                sp.id,
                P,
                RelationType.PRESENTS,
                sid,
                EntityType.SESSION,
                origin=Origin.EXPLICIT,
                method="sessionize_field",
                evidence="Listed as speaker in Sessionize",
            )
        if sp.company:
            org_name = normalize_org(sp.company)
            okey = f"organization:{slugify(org_name)}"
            if slugify(org_name) and slugify(org_name) not in self.non_orgs:
                self._entity(okey, EntityType.ORGANIZATION, org_name, Origin.EXPLICIT)
                self._rel(
                    sp.id,
                    P,
                    RelationType.ASSOCIATED_WITH,
                    okey,
                    EntityType.ORGANIZATION,
                    origin=Origin.EXPLICIT,
                    method="sessionize_question",
                    evidence=f"Company: {sp.company}",
                )
        refs: list[EntityRef] = []
        if sp.bio:
            for m in match_text(self.vocab, "", sp.bio):
                if m.entry.type not in (EntityType.PROJECT, EntityType.TECHNOLOGY):
                    continue
                self._vocab_entity(m.entry.key)
                role = bool(_ROLE_WORDS.search(m.evidence))
                rtype = RelationType.WORKS_ON if role else RelationType.RELATED_TO
                conf = 0.8 if role else 0.6
                self._rel(
                    sp.id,
                    P,
                    rtype,
                    m.entry.key,
                    m.entry.type,
                    origin=Origin.EXTRACTED,
                    method="bio_mention" + ("_role" if role else ""),
                    confidence=conf,
                    evidence=m.evidence,
                )
                refs.append(
                    EntityRef(
                        id=m.entry.key,
                        name=m.entry.name,
                        type=m.entry.type,
                        origin=Origin.EXTRACTED,
                        confidence=conf,
                        evidence=m.evidence,
                    )
                )
        sp.entities = refs

    def _maintainer_inference(self, sessions: list[Session], speakers: dict[str, Speaker]) -> None:
        """Speakers presenting a project-tagged Maintainer Track session likely work on it."""
        for s in sessions:
            if not s.track or "maintainer" not in s.track.lower():
                continue
            projects = [
                r
                for r in s.entities
                if r.type == EntityType.PROJECT and r.origin == Origin.EXPLICIT
            ]
            for sp_id in s.speaker_ids:
                if sp_id not in speakers:
                    continue
                for p in projects:
                    self._rel(
                        sp_id,
                        EntityType.SPEAKER,
                        RelationType.WORKS_ON,
                        p.id,
                        p.type,
                        origin=Origin.INFERRED,
                        method="maintainer_track_session",
                        confidence=0.75,
                        evidence=f"Presents Maintainer Track session '{s.title}'",
                    )

    def _curated_hierarchy(self) -> None:
        present = [k for k in self.entities if k in self.vocab.entries]
        for key in present:
            entry = self.vocab.entries[key]
            for parent_slug in entry.parents:
                parent = self.vocab.by_slug[parent_slug]
                self._vocab_entity(parent.key)
                self._rel(
                    key,
                    entry.type,
                    RelationType.PART_OF,
                    parent.key,
                    parent.type,
                    origin=Origin.CURATED,
                    method="vocabulary_hierarchy",
                    evidence=f"{entry.name} is curated under {parent.name}",
                )

    def _cooccurrence(self, sessions: list[Session], min_count: int = 3) -> None:
        n = len(sessions)
        freq: Counter[str] = Counter()
        pair: Counter[tuple[str, str]] = Counter()
        example: dict[tuple[str, str], str] = {}
        for s in sessions:
            keys = sorted({r.id for r in s.entities})
            freq.update(keys)
            for a, b in combinations(keys, 2):
                pair[(a, b)] += 1
                example.setdefault((a, b), s.title)
        for (a, b), c in pair.items():
            if c < min_count:
                continue
            lift = (c * n) / (freq[a] * freq[b])
            if lift < 1.5:
                continue
            ea, eb = self.entities[a], self.entities[b]
            conf = min(0.9, 0.4 + 0.1 * c)
            self._rel(
                a,
                ea.type,
                RelationType.RELATED_TO,
                b,
                eb.type,
                origin=Origin.INFERRED,
                method="co_occurrence",
                confidence=conf,
                weight=round(lift, 2),
                evidence=f"Co-occur in {c} sessions (lift {lift:.1f}), e.g. '{example[(a, b)]}'",
            )

    def _related_sessions(
        self,
        sessions: list[Session],
        vectors: np.ndarray | None,
        top_k: int = 6,
        threshold: float = 0.35,
        cos_floor: float = 0.70,
        cos_ceiling: float = 0.90,
    ) -> int:
        """RELATED_TO between sessions from abstract similarity + shared specific entities.

        bge-small cosines between sessions at this event are compressed (median ~0.66,
        p99 ~0.82, measured 2026-11-09), so cosine is rescaled from [floor, ceiling] to
        [0, 1] before mixing; raw cosine alone would link nearly everything.
        """
        content = [(i, s) for i, s in enumerate(sessions) if s.is_content]
        ent_sets = {s.id: {r.id for r in s.entities} - self.vocab.low_signal for _, s in content}
        sims: np.ndarray | None = None
        if vectors is not None and len(vectors) == len(sessions):
            sub = vectors[[i for i, _ in content]]
            sims = sub @ sub.T
        count = 0
        for a_pos, (_, sa) in enumerate(content):
            scored: list[tuple[float, str, float, list[str]]] = []
            for b_pos, (_, sb) in enumerate(content):
                if sa.id == sb.id or sa.title == sb.title:
                    continue
                inter = ent_sets[sa.id] & ent_sets[sb.id]
                union = ent_sets[sa.id] | ent_sets[sb.id]
                jac = len(inter) / len(union) if union else 0.0
                cos = float(sims[a_pos, b_pos]) if sims is not None else 0.0
                cos_r = min(1.0, max(0.0, (cos - cos_floor) / (cos_ceiling - cos_floor)))
                score = 0.6 * cos_r + 0.4 * jac if sims is not None else jac
                if score >= threshold:
                    names = sorted(self.entities[k].name for k in inter)
                    scored.append((score, sb.id, cos, names))
            for score, sb_id, cos, names in sorted(scored, reverse=True)[:top_k]:
                parts = []
                if names:
                    parts.append("Shares " + ", ".join(names[:4]))
                if sims is not None:
                    parts.append(f"abstract similarity {cos:.2f}")
                self._rel(
                    sa.id,
                    EntityType.SESSION,
                    RelationType.RELATED_TO,
                    sb_id,
                    EntityType.SESSION,
                    origin=Origin.INFERRED,
                    method="embedding_and_entity_overlap" if sims is not None else "entity_overlap",
                    confidence=round(min(0.95, score), 3),
                    weight=round(score, 4),
                    evidence="; ".join(parts),
                )
                count += 1
        return count

    def _counts(self, sessions: list[Session], speakers: list[Speaker]) -> None:
        sess_by_entity: defaultdict[str, set[str]] = defaultdict(set)
        spk_by_entity: defaultdict[str, set[str]] = defaultdict(set)
        for r in self.rels.values():
            if r.source_type == EntityType.SESSION and r.type != RelationType.RELATED_TO:
                sess_by_entity[r.target_id].add(r.source_id)
            if r.source_type == EntityType.SPEAKER and r.type != RelationType.PRESENTS:
                spk_by_entity[r.target_id].add(r.source_id)
        # Organizations: count sessions through their speakers.
        spk_sessions = {sp.id: set(sp.session_ids) for sp in speakers}
        for r in self.rels.values():
            if r.type == RelationType.ASSOCIATED_WITH:
                sess_by_entity[r.target_id] |= spk_sessions.get(r.source_id, set())
        for key, e in self.entities.items():
            e.session_count = len(sess_by_entity.get(key, ()))
            e.speaker_count = len(spk_by_entity.get(key, ()))
