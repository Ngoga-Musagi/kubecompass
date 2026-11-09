from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.ingestion.base import SourceValidationError
from app.ingestion.sessionize.adapter import SessionizeAdapter
from tests.conftest import make_payload, session_raw

NOW = datetime(2026, 11, 9, 17, 0, tzinfo=UTC)


def normalize(payload, conference):
    return SessionizeAdapter(min_sessions=1).normalize(payload, conference, NOW, "v-test")


# ---- real data ---------------------------------------------------------------------------
def test_real_counts_match_source(normalized):
    assert len(normalized.sessions) == 600
    assert len(normalized.speakers) == 712
    assert normalized.rejected == []


def test_real_speaker_session_relationships_are_preserved(normalized):
    sessions = {s.id: s for s in normalized.sessions}
    for sp in normalized.speakers:
        for sid in sp.session_ids:
            assert sp.id in sessions[sid].speaker_ids
    # Every session->speaker reference resolves.
    speaker_ids = {sp.id for sp in normalized.speakers}
    assert all(i in speaker_ids for s in normalized.sessions for i in s.speaker_ids)


def test_real_provenance_and_source_ids(normalized):
    s = normalized.sessions[0]
    assert s.id == f"kubecon-na-2026:{s.source_id}"
    assert s.provenance.source_system == "sessionize"
    assert s.provenance.source_url.startswith("https://sessionize.com/api/v2/")
    assert s.provenance.payload_hash and len(s.provenance.payload_hash) == 64


def test_real_times_are_denver_local_with_correct_offset(normalized):
    s = next(x for x in normalized.sessions if x.time and x.time.day == "2026-11-10")
    assert s.time.timezone == "America/Denver"
    # DST ended 2026-11-01, so the conference runs on MST (UTC-7).
    assert s.time.starts_at.utcoffset() == timedelta(hours=-7)
    assert s.time.starts_at.isoformat().startswith(s.time.starts_at_local)


def test_real_missing_descriptions_are_not_fabricated(normalized):
    missing = [s for s in normalized.sessions if s.description is None]
    assert len(missing) == 47


def test_real_breaks_inside_talk_tracks_are_not_content(normalized):
    coffee = [s for s in normalized.sessions if "Coffee Break" in s.title]
    assert coffee and all(s.format == "break" and not s.is_content for s in coffee)


# ---- edge cases --------------------------------------------------------------------------
def test_track_format_level_and_emoji_normalization(conference):
    p = make_payload(
        [session_raw("1", "Lightning: Fast", cats=[12, 20], speakers=["s1"])],
        speakers=[{"id": "s1", "fullName": "Ann Bee", "sessions": [1]}],
    )
    s = normalize(p, conference).sessions[0]
    assert s.track == "Lightning Talks"
    assert s.format == "lightning_talk" and s.format_origin == "category"
    assert s.audience_level == "Advanced"


def test_panel_detected_from_title_with_origin(conference):
    p = make_payload(
        [session_raw("1", "Panel: The Future of Inference", speakers=["s1"])],
        speakers=[{"id": "s1", "fullName": "Ann Bee", "sessions": [1]}],
    )
    s = normalize(p, conference).sessions[0]
    assert (s.format, s.format_origin) == ("panel", "title_pattern")


def test_duplicate_ids_and_slots_rejected(conference):
    sessions = [
        session_raw("1", "Talk A"),
        session_raw("1", "Talk A copy"),
        session_raw("2", "Same Slot"),
        session_raw("3", "same slot"),
    ]
    out = normalize(make_payload(sessions), conference)
    assert [s.source_id for s in out.sessions] == ["1", "2"]
    reasons = {r["id"]: r["reason"] for r in out.rejected}
    assert reasons["1"] == "duplicate id"
    assert "duplicate of 2" in reasons["3"]


def test_recurring_titles_kept_separately(conference):
    sessions = [
        session_raw("1", "Office Hours"),
        session_raw("2", "Office Hours", start="2026-11-11T11:00:00", end="2026-11-11T11:30:00"),
    ]
    out = normalize(make_payload(sessions), conference)
    assert len(out.sessions) == 2
    assert any("recurring" in i for i in out.issues)


def test_missing_time_is_unavailable_not_invented(conference):
    raw = session_raw("1", "No time yet", start=None, end=None)  # type: ignore[arg-type]
    out = normalize(make_payload([raw]), conference)
    assert out.sessions[0].time is None
    assert any("missing start/end" in i for i in out.issues)


def test_room_venue_parsed(conference):
    out = normalize(make_payload([session_raw("1", "X", room=101)]), conference)
    assert out.sessions[0].room.venue == "Hyatt Regency"


def test_invalid_json_rejected(conference):
    p = make_payload([session_raw(str(i), f"T{i}") for i in range(12)])
    bad = type(p)(b"{not json", p.speakers_raw, p.origin, p.retrieved_at, p.locations)
    with pytest.raises(SourceValidationError):
        SessionizeAdapter().validate(bad)


def test_truncated_payload_rejected(conference):
    p = make_payload([session_raw("1", "Only one")])
    with pytest.raises(SourceValidationError, match="refusing"):
        SessionizeAdapter().validate(p)


def test_schema_violation_rejected(conference):
    p = make_payload([{"id": "1"}])  # no title
    with pytest.raises(SourceValidationError, match="schema"):
        SessionizeAdapter().validate(p)
