"""End-to-end ingestion: load -> validate -> normalize -> extract -> embed -> snapshot -> index."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from app.config.conferences import ConferenceConfig
from app.config.settings import Settings
from app.domain.models import Conference, Dataset, EntityType, Session, Speaker
from app.infrastructure.calibration import calibration_for
from app.infrastructure.embeddings import EmbeddingCache, EmbeddingProvider
from app.ingestion.base import IngestionAdapter, SourceValidationError
from app.ingestion.diff import diff_sessions
from app.ingestion.sessionize.adapter import SessionizeAdapter
from app.ingestion.snapshot import IngestionStatus, SnapshotStore
from app.knowledge_graph.builder import KnowledgeGraphBuilder
from app.knowledge_graph.vocabulary import Vocabulary
from app.search.indexer import Indexer

log = logging.getLogger(__name__)

ADAPTERS: dict[str, type] = {"sessionize": SessionizeAdapter}
# A refresh that loses more than this share of sessions is treated as suspect.
MAX_SESSION_DROP = 0.3


def session_embedding_text(s: Session) -> str:
    parts = [s.title]
    if s.track:
        parts.append(f"Track: {s.track}")
    names = [r.name for r in s.entities[:12]]
    if names:
        parts.append("Topics: " + ", ".join(names))
    if s.description:
        parts.append(s.description[:2000])
    return "\n".join(parts)


def speaker_embedding_text(sp: Speaker, titles: list[str]) -> str:
    parts = [sp.full_name]
    if sp.tagline:
        parts.append(sp.tagline)
    if titles:
        parts.append("Talks: " + "; ".join(titles))
    if sp.bio:
        parts.append(sp.bio[:1500])
    return "\n".join(parts)


@dataclass
class IngestionResult:
    status: IngestionStatus
    dataset: Dataset | None


class IngestionPipeline:
    def __init__(
        self,
        settings: Settings,
        conference: ConferenceConfig,
        vocabulary: Vocabulary,
        embeddings: EmbeddingProvider,
        indexer: Indexer | None,
    ) -> None:
        self.settings = settings
        self.conf = conference
        self.vocab = vocabulary
        self.embeddings = embeddings
        self.indexer = indexer
        self.store = SnapshotStore(settings.data_dir / "processed", conference.id)
        adapter_cls = ADAPTERS.get(conference.source.adapter)
        if adapter_cls is None:
            raise ValueError(f"No ingestion adapter named {conference.source.adapter!r}")
        self.adapter: IngestionAdapter = adapter_cls()

    def run(
        self, *, remote: bool = False, force: bool = False, index: bool = True
    ) -> IngestionResult:
        started = datetime.now(UTC)
        previous = self.store.load_current()
        prev_status = self.store.load_status()
        status = IngestionStatus(
            conference_id=self.conf.id,
            state="failed",
            started_at=started,
            finished_at=started,
            last_successful_version=prev_status.last_successful_version if prev_status else None,
            last_successful_at=prev_status.last_successful_at if prev_status else None,
        )
        try:
            payload = (
                self.adapter.fetch_remote(self.conf)
                if remote
                else self.adapter.load_local(self.conf)
            )
            status.origin = payload.origin
            status.source_retrieved_at = payload.retrieved_at
            digest = hashlib.sha256(payload.sessions_raw + payload.speakers_raw).hexdigest()[:8]
            version = f"{started.strftime('%Y%m%dT%H%M%SZ')}-{digest}"
            status.ingestion_version = version

            normalized = self.adapter.normalize(payload, self.conf, started, version)
            status.issues = normalized.issues
            status.rejected = normalized.rejected

            if previous and not force:
                old_n, new_n = len(previous.sessions), len(normalized.sessions)
                if old_n and (old_n - new_n) / old_n > MAX_SESSION_DROP:
                    raise SourceValidationError(
                        f"Refresh would drop sessions from {old_n} to {new_n}; keeping previous "
                        "snapshot (use --force to override)"
                    )

            # Entities need to exist before embedding (embedding text includes topics); related
            # sessions need embeddings, so extraction runs in two passes over the same builder.
            non_orgs = self.conf.non_organization_values
            pre = KnowledgeGraphBuilder(self.vocab, self.conf.id, non_orgs)
            for s in normalized.sessions:
                pre.add_session(s)
            session_vecs, speaker_vecs = self._embed(normalized.sessions, normalized.speakers)
            matrix = (
                np.stack([session_vecs[s.id] for s in normalized.sessions])
                if session_vecs
                else None
            )
            cal = calibration_for(self.embeddings.model_name)
            graph = KnowledgeGraphBuilder(
                self.vocab, self.conf.id, non_orgs, (cal.related_floor, cal.related_ceiling)
            ).build(normalized.sessions, normalized.speakers, matrix)
            dataset = self._dataset(
                normalized, graph.entities, graph.relationships, version, started
            )
            status.counts = {
                "sessions": len(dataset.sessions),
                "content_sessions": sum(1 for s in dataset.sessions if s.is_content),
                "speakers": len(dataset.speakers),
                "rooms": len(dataset.rooms),
                "tracks": len(dataset.tracks),
                "rejected": len(normalized.rejected),
                "issues": len(normalized.issues),
                "embedded_sessions": len(session_vecs),
                "embedded_speakers": len(speaker_vecs),
            }
            status.graph_stats = graph.stats

            changes = (
                diff_sessions(previous.sessions if previous else [], dataset.sessions, started)
                if previous
                else []
            )
            status.changes = {
                k: sum(1 for c in changes if c.change == k)
                for k in ("added", "removed", "modified")
            }

            # Index first: if indexing fails the on-disk snapshot also stays at the old version,
            # keeping disk and search consistent.
            if index and self.indexer is not None:
                self.indexer.index_dataset(dataset, session_vecs, speaker_vecs)
                self.indexer.record_changes(self.conf.id, version, changes)
                status.indexed = True
            self.store.save(dataset)
            if changes:
                self.store.append_changes(changes)

            status.state = "succeeded"
            status.last_successful_version = version
            status.last_successful_at = datetime.now(UTC)
            result_ds: Dataset | None = dataset
        except SourceValidationError as exc:
            status.state = "rejected"
            status.error = str(exc)
            result_ds = None
            log.error("Ingestion rejected for %s: %s", self.conf.id, exc)
        except Exception as exc:
            status.state = "failed"
            status.error = f"{type(exc).__name__}: {exc}"
            result_ds = None
            log.exception("Ingestion failed for %s", self.conf.id)
        status.finished_at = datetime.now(UTC)
        self.store.save_status(status)
        return IngestionResult(status=status, dataset=result_ds)

    def _embed(
        self, sessions: list[Session], speakers: list[Speaker]
    ) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
        if not self.embeddings.available:
            log.warning("Embeddings unavailable; indexing without vectors (BM25 only)")
            return {}, {}
        cache = EmbeddingCache(
            self.settings.data_dir / "processed" / self.conf.id / "embeddings.npz",
            self.embeddings.model_name,
        )
        s_vecs = cache.embed(self.embeddings, [session_embedding_text(s) for s in sessions])
        titles = {s.id: s.title for s in sessions}
        sp_texts = [
            speaker_embedding_text(sp, [titles[i] for i in sp.session_ids if i in titles])
            for sp in speakers
        ]
        p_vecs = cache.embed(self.embeddings, sp_texts) if speakers else np.zeros((0, 1))
        return (
            {s.id: v for s, v in zip(sessions, s_vecs, strict=True)},
            {sp.id: v for sp, v in zip(speakers, p_vecs, strict=True)},
        )

    def _dataset(self, normalized, entities, relationships, version: str, now: datetime) -> Dataset:  # type: ignore[no-untyped-def]
        days = sorted({s.time.day for s in normalized.sessions if s.time})
        conference = Conference(
            id=self.conf.id,
            name=self.conf.name,
            short_name=self.conf.short_name,
            city=self.conf.city,
            timezone=self.conf.timezone,
            website=self.conf.website,
            start_date=days[0] if days else None,
            end_date=days[-1] if days else None,
            session_count=len(normalized.sessions),
            speaker_count=len(normalized.speakers),
            last_refreshed_at=now,
            data_version=version,
        )
        return Dataset(
            conference=conference,
            sessions=normalized.sessions,
            speakers=normalized.speakers,
            entities=[
                e for e in entities if e.type not in (EntityType.SESSION, EntityType.SPEAKER)
            ],
            relationships=relationships,
            rooms=normalized.rooms,
            tracks=normalized.tracks,
            issues=normalized.issues,
            ingestion_version=version,
            created_at=now,
        )
