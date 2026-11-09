"""Index a validated Dataset into Elasticsearch with an atomic alias swap.

New documents go into fresh, versioned physical indices. The read aliases are
switched only after every bulk load succeeds, so a failed indexing run leaves
the previously indexed data serving traffic.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from typing import Any

import numpy as np
from elasticsearch import Elasticsearch, helpers

from app.config.settings import get_settings
from app.domain.models import Dataset, EntityType, RelationType, Session, Speaker
from app.infrastructure.elasticsearch import (
    INDEX_KINDS,
    alias,
    ensure_state_indices,
    index_body,
    physical_index,
)
from app.ingestion.snapshot import SessionChange

log = logging.getLogger(__name__)


def session_doc(s: Session, vector: np.ndarray | None) -> dict[str, Any]:
    by_type: dict[EntityType, list[str]] = {}
    for r in s.entities:
        by_type.setdefault(r.type, []).append(r.name)
    doc: dict[str, Any] = {
        "id": s.id,
        "conference_id": s.conference_id,
        "source_id": s.source_id,
        "title": s.title,
        "description": s.description,
        "track": s.track,
        "subtopics": s.subtopics,
        "audience_level": s.audience_level,
        "format": s.format,
        "format_origin": s.format_origin,
        "flags": s.flags,
        "project_tags": s.project_tags,
        "speaker_ids": s.speaker_ids,
        "speaker_names": s.speaker_names,
        "speaker_companies": [],
        "entity_ids": [r.id for r in s.entities],
        "entity_names": [r.name for r in s.entities],
        "topics": by_type.get(EntityType.TOPIC, []),
        "technologies": by_type.get(EntityType.TECHNOLOGY, []),
        "projects": by_type.get(EntityType.PROJECT, []),
        "starts_at": s.time.starts_at.isoformat() if s.time else None,
        "ends_at": s.time.ends_at.isoformat() if s.time else None,
        "starts_at_local": s.time.starts_at_local if s.time else None,
        "day": s.time.day if s.time else None,
        "duration_minutes": s.time.duration_minutes if s.time else None,
        "room_id": s.room.id if s.room else None,
        "room_name": s.room.name if s.room else None,
        "venue": s.room.venue if s.room else None,
        "is_content": s.is_content,
        "has_resources": bool(s.resources),
        "status": s.status,
        "doc": s.model_dump(mode="json"),
    }
    if vector is not None:
        doc["embedding"] = vector.tolist()
    if get_settings().semantic_text_inference_id:
        parts = [
            s.title,
            s.track,
            ", ".join(r.name for r in s.entities[:12]),
            (s.description or "")[:4000],
        ]
        doc["semantic_content"] = "\n".join(p for p in parts if p)
    return doc


def speaker_doc(
    sp: Speaker, sessions: dict[str, Session], vector: np.ndarray | None
) -> dict[str, Any]:
    own = [sessions[sid] for sid in sp.session_ids if sid in sessions]
    doc: dict[str, Any] = {
        "id": sp.id,
        "conference_id": sp.conference_id,
        "source_id": sp.source_id,
        "full_name": sp.full_name,
        "tagline": sp.tagline,
        "bio": sp.bio,
        "company": sp.company,
        "job_title": sp.job_title,
        "session_ids": sp.session_ids,
        "session_titles": [s.title for s in own],
        "tracks": sorted({s.track for s in own if s.track}),
        "entity_ids": sorted({r.id for r in sp.entities} | {r.id for s in own for r in s.entities}),
        "entity_names": sorted(
            {r.name for r in sp.entities} | {r.name for s in own for r in s.entities}
        ),
        "is_top_speaker": sp.is_top_speaker,
        "session_count": len(own),
        "doc": sp.model_dump(mode="json"),
    }
    if vector is not None:
        doc["embedding"] = vector.tolist()
    return doc


class Indexer:
    def __init__(self, es: Elasticsearch, embedding_dims: int | None) -> None:
        self.es = es
        self.dims = embedding_dims

    def _bulk(self, index: str, docs: Iterable[dict[str, Any]]) -> int:
        def actions() -> Iterator[dict[str, Any]]:
            for d in docs:
                yield {"_index": index, "_id": d["id"], "_source": d}

        ok, errors = helpers.bulk(
            self.es.options(request_timeout=120), actions(), chunk_size=200, raise_on_error=False
        )
        errors = errors if isinstance(errors, list) else []
        if errors:
            raise RuntimeError(f"Bulk indexing into {index} had {len(errors)} errors: {errors[:2]}")
        return int(ok)

    def index_dataset(
        self,
        dataset: Dataset,
        session_vectors: dict[str, np.ndarray],
        speaker_vectors: dict[str, np.ndarray],
    ) -> dict[str, int]:
        cid = dataset.conference.id
        version = dataset.ingestion_version
        sessions = {s.id: s for s in dataset.sessions}
        companies: dict[str, list[str]] = {}
        sp_by_id = {sp.id: sp for sp in dataset.speakers}
        for s in dataset.sessions:
            companies[s.id] = sorted(
                {
                    company
                    for i in s.speaker_ids
                    if i in sp_by_id and (company := sp_by_id[i].company)
                }
            )  # type: ignore[misc]

        new_indices = {k: physical_index(k, cid, version) for k in INDEX_KINDS}
        dims = self.dims if session_vectors else None
        for kind, name in new_indices.items():
            if self.es.indices.exists(index=name):
                self.es.indices.delete(index=name)
            body = index_body(kind, dims)
            if dims is None and "embedding" in body["mappings"]["properties"]:
                del body["mappings"]["properties"]["embedding"]
            self.es.indices.create(index=name, **body)

        counts: dict[str, int] = {}
        try:

            def sdocs() -> Iterator[dict[str, Any]]:
                for s in dataset.sessions:
                    d = session_doc(s, session_vectors.get(s.id))
                    d["speaker_companies"] = companies.get(s.id, [])
                    yield d

            counts["sessions"] = self._bulk(new_indices["sessions"], sdocs())
            counts["speakers"] = self._bulk(
                new_indices["speakers"],
                (speaker_doc(sp, sessions, speaker_vectors.get(sp.id)) for sp in dataset.speakers),
            )
            counts["entities"] = self._bulk(
                new_indices["entities"],
                (
                    {**e.model_dump(mode="json"), "id": e.id}
                    for e in dataset.entities
                    if e.type not in (EntityType.SESSION, EntityType.SPEAKER)
                ),
            )
            counts["relationships"] = self._bulk(
                new_indices["relationships"],
                (
                    r.model_dump(mode="json")
                    for r in dataset.relationships
                    if r.type != RelationType.SCHEDULED_IN
                ),
            )
            for name in new_indices.values():
                self.es.indices.refresh(index=name)
        except Exception:
            for name in new_indices.values():
                self.es.indices.delete(index=name, ignore_unavailable=True)
            raise

        self._swap_aliases(cid, new_indices)
        ensure_state_indices(self.es)
        return counts

    def _swap_aliases(self, cid: str, new_indices: dict[str, str]) -> None:
        actions: list[dict[str, Any]] = []
        stale: list[str] = []
        for kind, new in new_indices.items():
            a = alias(kind)
            pattern = f"{a}__{cid}__*"
            existing = list(self.es.indices.get(index=pattern, ignore_unavailable=True).keys())
            for old in existing:
                if old != new:
                    actions.append({"remove": {"index": old, "alias": a}})
                    stale.append(old)
            actions.append({"add": {"index": new, "alias": a}})
        self.es.indices.update_aliases(actions=actions)
        # Keep only the immediately previous version for manual rollback.
        for kind in new_indices:
            olds = sorted(i for i in stale if i.startswith(f"{alias(kind)}__"))
            for name in olds[:-1]:
                self.es.indices.delete(index=name, ignore_unavailable=True)

    def record_changes(self, cid: str, version: str, changes: list[SessionChange]) -> None:
        if not changes:
            return
        ensure_state_indices(self.es)

        def actions() -> Iterator[dict[str, Any]]:
            for c in changes:
                yield {
                    "_index": alias("changes"),
                    "_source": {
                        **c.model_dump(mode="json"),
                        "conference_id": cid,
                        "ingestion_version": version,
                    },
                }

        helpers.bulk(self.es, actions(), raise_on_error=True)
