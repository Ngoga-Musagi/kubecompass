from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config.conferences import get_conference
from app.config.settings import get_settings
from app.ingestion.base import SourcePayload
from app.ingestion.sessionize.adapter import SessionizeAdapter
from app.knowledge_graph.vocabulary import get_vocabulary

ROOT = get_settings().repo_root
RAW = ROOT / "data" / "raw"


@pytest.fixture(scope="session")
def conference():
    return get_conference("kubecon-na-2026")


@pytest.fixture(scope="session")
def vocabulary():
    return get_vocabulary()


@pytest.fixture(scope="session")
def real_payload() -> SourcePayload:
    if not (RAW / "kubecon-all.json").exists():
        pytest.skip("real Sessionize files not present in data/raw")
    return SourcePayload(
        sessions_raw=(RAW / "kubecon-all.json").read_bytes(),
        speakers_raw=(RAW / "kubecon-speakers.json").read_bytes(),
        origin="local_file",
        retrieved_at=datetime.now(UTC),
        locations=("all", "speakers"),
    )


@pytest.fixture(scope="session")
def normalized(real_payload, conference):
    return SessionizeAdapter().normalize(real_payload, conference, datetime.now(UTC), "test")


def make_payload(
    sessions: list[dict],
    speakers: list[dict] | None = None,
    categories: list[dict] | None = None,
    rooms: list[dict] | None = None,
) -> SourcePayload:
    """Minimal Sessionize-shaped payload for edge-case tests."""
    speakers = speakers or []
    all_view = {
        "sessions": sessions,
        "speakers": [
            {
                "id": s["id"],
                "firstName": "A",
                "lastName": "B",
                "fullName": s["fullName"],
                "bio": s.get("bio"),
                "tagLine": None,
                "profilePicture": None,
                "isTopSpeaker": False,
                "links": [],
                "sessions": s.get("sessions", []),
                "questionAnswers": s.get("questionAnswers", []),
            }
            for s in speakers
        ],
        "questions": [
            {"id": 128829, "question": "Company", "questionType": "Short_Text"},
            {"id": 137003, "question": "Presentation Slides", "questionType": "File_upload"},
        ],
        "categories": categories
        if categories is not None
        else [
            {
                "id": 1,
                "title": "All Sessions",
                "type": "session",
                "items": [
                    {"id": 10, "name": "Observability"},
                    {"id": 11, "name": "Breaks"},
                    {"id": 12, "name": "⚡ Lightning Talks"},
                ],
            },
            {
                "id": 2,
                "title": "Audience Level",
                "type": "session",
                "items": [{"id": 20, "name": "Advanced"}],
            },
            {
                "id": 3,
                "title": "CNCF Projects",
                "type": "session",
                "items": [
                    {"id": 30, "name": "OpenTelemetry"},
                    {"id": 31, "name": "Brand New Proj"},
                ],
            },
        ],
        "rooms": rooms
        if rooms is not None
        else [
            {"id": 100, "name": "Salt Palace | Level 2 | 250 A-C"},
            {"id": 101, "name": "Hyatt Regency | Level 4 | Regency Ballroom A"},
        ],
    }
    spk_view = [
        {
            "id": s["id"],
            "fullName": s["fullName"],
            "bio": s.get("bio"),
            "sessions": [{"id": x, "name": "t"} for x in s.get("sessions", [])],
            "questionAnswers": [],
            "links": [],
            "categories": [],
        }
        for s in speakers
    ]
    return SourcePayload(
        sessions_raw=json.dumps(all_view).encode(),
        speakers_raw=json.dumps(spk_view).encode(),
        origin="local_file",
        retrieved_at=datetime.now(UTC),
        locations=("a", "b"),
    )


def session_raw(
    sid: str,
    title: str,
    start: str = "2026-11-10T11:00:00",
    end: str = "2026-11-10T11:30:00",
    room: int | None = 100,
    cats: list[int] | None = None,
    speakers: list[str] | None = None,
    description: str | None = "An abstract.",
) -> dict:
    return {
        "id": sid,
        "title": title,
        "description": description,
        "startsAt": start,
        "endsAt": end,
        "isServiceSession": False,
        "isPlenumSession": False,
        "speakers": speakers or [],
        "categoryItems": cats or [10],
        "questionAnswers": [],
        "roomId": room,
        "liveUrl": None,
        "recordingUrl": None,
        "status": "Accepted",
    }


def es_available() -> bool:
    url = os.environ.get("KUBECOMPASS_TEST_ES_URL", "http://localhost:9200")
    try:
        import httpx

        return httpx.get(url, timeout=2).status_code == 200
    except Exception:
        return False


def rel_path(p: Path) -> str:
    return str(p.relative_to(ROOT))
