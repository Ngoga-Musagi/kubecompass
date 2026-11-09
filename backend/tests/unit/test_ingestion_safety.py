"""Refresh safety: invalid or suspicious refreshes never replace the last valid snapshot."""

from __future__ import annotations

from datetime import UTC, datetime

from app.config.settings import get_settings
from app.infrastructure.embeddings import NullEmbeddingProvider
from app.ingestion.diff import diff_sessions
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.sessionize.adapter import SessionizeAdapter
from tests.conftest import make_payload, session_raw


class _Adapter(SessionizeAdapter):
    def __init__(self, payload):
        super().__init__()
        self.payload = payload

    def load_local(self, conference):
        return self.payload


def _pipeline(tmp_path, conference, vocabulary, payload):
    settings = get_settings().model_copy(update={"repo_root": tmp_path})
    p = IngestionPipeline(settings, conference, vocabulary, NullEmbeddingProvider(), None)
    p.adapter = _Adapter(payload)
    return p


def _sessions(n: int):
    return [
        session_raw(
            str(i),
            f"Talk {i}",
            start=f"2026-11-10T{8 + i % 10:02d}:{i % 6}0:00",
            end=f"2026-11-10T{8 + i % 10:02d}:{i % 6}5:00",
            room=100 + i % 2,
        )
        for i in range(n)
    ]


def test_valid_then_invalid_refresh_keeps_previous(tmp_path, conference, vocabulary):
    first = _pipeline(tmp_path, conference, vocabulary, make_payload(_sessions(20))).run(
        index=False
    )
    assert first.status.state == "succeeded"
    v1 = first.status.ingestion_version

    bad = make_payload(_sessions(20))
    bad = type(bad)(
        b"<html>maintenance</html>", bad.speakers_raw, bad.origin, bad.retrieved_at, bad.locations
    )
    second = _pipeline(tmp_path, conference, vocabulary, bad).run(index=False)
    assert second.status.state == "rejected"
    assert second.status.last_successful_version == v1
    store = _pipeline(tmp_path, conference, vocabulary, bad).store
    assert store.load_current().ingestion_version == v1


def test_large_drop_requires_force(tmp_path, conference, vocabulary):
    _pipeline(tmp_path, conference, vocabulary, make_payload(_sessions(30))).run(index=False)
    shrunk = _pipeline(tmp_path, conference, vocabulary, make_payload(_sessions(12)))
    assert shrunk.run(index=False).status.state == "rejected"
    assert shrunk.run(index=False, force=True).status.state == "succeeded"


def test_diff_detects_additions_removals_and_room_change(conference):
    now = datetime.now(UTC)
    a = SessionizeAdapter()
    old = a.normalize(make_payload(_sessions(12)), conference, now, "v1").sessions
    updated = [s for s in _sessions(12) if s["id"] != "5"]  # one removed
    updated[0]["roomId"] = 101 if updated[0]["roomId"] == 100 else 100  # one moved
    updated.append(
        session_raw("99", "New talk", start="2026-11-11T10:00:00", end="2026-11-11T10:30:00")
    )  # one added
    new = a.normalize(make_payload(updated), conference, now, "v2").sessions
    changes = {(c.session_id.split(":")[1], c.change): c for c in diff_sessions(old, new, now)}
    assert ("99", "added") in changes
    assert ("5", "removed") in changes
    assert changes[("0", "modified")].fields == ["room"]
