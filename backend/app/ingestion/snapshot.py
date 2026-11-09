"""On-disk snapshot store: the last valid dataset is replaced only, and atomically, by a newer
valid one."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from app.domain.models import Dataset


class SessionChange(BaseModel):
    session_id: str
    title: str
    change: str  # added | removed | modified
    fields: list[str] = Field(default_factory=list)
    before: dict[str, str | None] = Field(default_factory=dict)
    after: dict[str, str | None] = Field(default_factory=dict)
    detected_at: datetime


class IngestionStatus(BaseModel):
    conference_id: str
    state: str  # succeeded | failed | rejected
    started_at: datetime
    finished_at: datetime
    origin: str | None = None
    ingestion_version: str | None = None
    last_successful_version: str | None = None
    last_successful_at: datetime | None = None
    source_retrieved_at: datetime | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    graph_stats: dict[str, int] = Field(default_factory=dict)
    changes: dict[str, int] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    rejected: list[dict[str, str]] = Field(default_factory=list)
    indexed: bool = False
    error: str | None = None


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class SnapshotStore:
    def __init__(self, processed_dir: Path, conference_id: str) -> None:
        self.dir = processed_dir / conference_id
        self.cid = conference_id

    @property
    def current_path(self) -> Path:
        return self.dir / "dataset.json"

    @property
    def status_path(self) -> Path:
        return self.dir / "ingestion-status.json"

    @property
    def changes_path(self) -> Path:
        return self.dir / "changes.json"

    def load_current(self) -> Dataset | None:
        if not self.current_path.exists():
            return None
        return Dataset.model_validate_json(self.current_path.read_text(encoding="utf-8"))

    def save(self, dataset: Dataset) -> None:
        payload = dataset.model_dump_json()
        archive = (
            self.dir / "history" / f"dataset-{dataset.ingestion_version.replace(':', '')}.json"
        )
        _atomic_write(archive, payload)
        _atomic_write(self.current_path, payload)
        self._prune_history(keep=5)

    def _prune_history(self, keep: int) -> None:
        files = sorted((self.dir / "history").glob("dataset-*.json"))
        for old in files[:-keep]:
            old.unlink(missing_ok=True)

    def load_status(self) -> IngestionStatus | None:
        if not self.status_path.exists():
            return None
        return IngestionStatus.model_validate_json(self.status_path.read_text(encoding="utf-8"))

    def save_status(self, status: IngestionStatus) -> None:
        _atomic_write(self.status_path, status.model_dump_json(indent=2))

    def load_changes(self) -> list[SessionChange]:
        if not self.changes_path.exists():
            return []
        data = json.loads(self.changes_path.read_text(encoding="utf-8"))
        return [SessionChange.model_validate(c) for c in data]

    def append_changes(self, changes: list[SessionChange], keep: int = 2000) -> None:
        merged = [*self.load_changes(), *changes][-keep:]
        _atomic_write(self.changes_path, json.dumps([c.model_dump(mode="json") for c in merged]))
