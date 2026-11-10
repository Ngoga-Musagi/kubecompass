"""End-to-end journey on REAL KubeCon data against a running Elasticsearch.

Sessionize JSON -> ingestion -> normalization -> entity/relationship extraction ->
ES indexing -> intent -> hybrid retrieval -> graph expansion -> recommendations ->
agenda (conflicts, alternatives) -> ICS export, all through the HTTP API.

Uses an isolated index prefix and data directory, so live indices are untouched.
Run: `make test-integration` (requires `docker compose up -d elasticsearch`).
"""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Iterator

import pytest

from tests.conftest import ROOT, es_available

pytestmark = pytest.mark.integration

PREFIX = "kctest"
GUEST = str(uuid.uuid4())
INTENT = (
    "I am building an AI-powered Kubernetes autoscaler. I want to understand production AI "
    "infrastructure, GPU scheduling, inference optimization, observability, agentic systems, and "
    "workload orchestration. I prefer advanced technical talks and demonstrations."
)


@pytest.fixture(scope="module")
def client(tmp_path_factory) -> Iterator:
    if not es_available():
        pytest.skip("Elasticsearch not reachable")
    data_root = tmp_path_factory.mktemp("data")
    cached = ROOT / "data" / "processed" / "kubecon-na-2026" / "embeddings.npz"
    if cached.exists():  # reuse content-addressed embedding cache to keep the test fast
        (data_root / "processed" / "kubecon-na-2026").mkdir(parents=True)
        shutil.copy(cached, data_root / "processed" / "kubecon-na-2026" / "embeddings.npz")
    # Always a local, disposable cluster: never the developer's (possibly cloud) .env target.
    os.environ["KUBECOMPASS_ES_URL"] = os.environ.get(
        "KUBECOMPASS_TEST_ES_URL", "http://localhost:9200"
    )
    os.environ["KUBECOMPASS_ES_API_KEY"] = ""
    os.environ["KUBECOMPASS_KIBANA_URL"] = ""
    os.environ["KUBECOMPASS_EMBEDDING_PROVIDER"] = "fastembed"
    os.environ["KUBECOMPASS_EMBEDDING_DIMENSIONS"] = "384"
    os.environ["KUBECOMPASS_SEMANTIC_TEXT_INFERENCE_ID"] = ""
    os.environ["KUBECOMPASS_ES_INDEX_PREFIX"] = PREFIX
    os.environ["KUBECOMPASS_DATA_ROOT"] = str(data_root)
    os.environ["KUBECOMPASS_LLM_PROVIDER"] = "none"  # deterministic, no network
    os.environ["KUBECOMPASS_ADMIN_TOKEN"] = "test-admin-token"

    from app.config.settings import get_settings
    from app.infrastructure.elasticsearch import get_es
    from app.services.container import get_container

    get_settings.cache_clear()
    get_es.cache_clear()
    get_container.cache_clear()

    from fastapi.testclient import TestClient

    from app.cli import main as cli_main
    from app.main import create_app

    assert cli_main(["ingest"]) == 0, "ingestion of real Sessionize data failed"
    with TestClient(create_app()) as c:
        c.headers["X-Guest-Id"] = GUEST
        yield c
    es = get_es()
    for idx in es.indices.get(index=f"{PREFIX}_*", ignore_unavailable=True):
        es.indices.delete(index=idx, ignore_unavailable=True)
    for k in (
        "KUBECOMPASS_ES_INDEX_PREFIX",
        "KUBECOMPASS_DATA_ROOT",
        "KUBECOMPASS_LLM_PROVIDER",
        "KUBECOMPASS_ADMIN_TOKEN",
    ):
        os.environ.pop(k, None)
    get_settings.cache_clear()
    get_es.cache_clear()
    get_container.cache_clear()


def test_health_and_conference(client):
    h = client.get("/api/health").json()
    assert h["elasticsearch"] == "ok" and "kubecon-na-2026" in h["indexed_conferences"]
    conf = client.get("/api/conferences/kubecon-na-2026").json()
    assert conf["session_count"] == 600 and conf["speaker_count"] == 712
    assert conf["timezone"] == "America/Denver"


def test_keyword_vector_hybrid_and_filters(client):
    for mode in ("keyword", "vector", "hybrid", "hybrid_native"):
        r = client.post("/api/discovery/search", json={"query": "GPU sharing", "mode": mode}).json()
        assert r["total"] > 0, mode
    day = "2026-11-11"
    r = client.post(
        "/api/discovery/search",
        json={
            "query": "observability",
            "mode": "hybrid",
            "filters": {"days": [day], "formats": ["talk"]},
        },
    ).json()
    assert r["hits"] and all(
        h["session"]["day"] == day and h["session"]["format"] == "talk" for h in r["hits"]
    )
    phrase = client.post("/api/discovery/search", json={"query": '"KV cache"', "mode": "keyword"})
    assert phrase.status_code == 200


def test_speaker_and_graph(client):
    sp = client.get("/api/speakers", params={"q": "scheduling"}).json()
    assert sp["items"]
    g = client.get("/api/knowledge-graph/neighborhood/topic:gpu-scheduling").json()
    assert g["center"] == "topic:gpu-scheduling" and len(g["nodes"]) > 3
    assert all(e["origin"] in {"explicit", "extracted", "inferred", "curated"} for e in g["edges"])
    assert client.get("/api/knowledge-graph/neighborhood/topic:not-real").status_code == 404


def test_intent_recommendations_agenda_and_ics(client):
    intent = client.post("/api/discovery/intent", json={"text": INTENT}).json()
    labels = {i["label"] for i in intent["profile"]["primary_interests"]}
    assert {"GPU Scheduling & Sharing", "AI Inference"} <= labels

    recs = client.post("/api/recommendations", json={}).json()
    must = recs["must_attend"]
    assert must, "expected Must Attend recommendations for the demo persona"
    for r in must:
        assert r["explanation"]["reasons"]
        desc = client.get(f"/api/sessions/{r['session']['id']}").json()["description"] or ""
        assert all(q in desc for q in r["explanation"]["learn"]), "learn quotes must be verbatim"
    assert recs["pipeline"]["graph_expanded"] > 0

    # Two overlapping talks -> conflict -> alternatives -> ICS.
    page = client.get(
        "/api/sessions", params={"day": "2026-11-11", "format": "talk", "limit": 200}
    ).json()["items"]
    a, b = next(
        (x, y)
        for i, x in enumerate(page)
        for y in page[i + 1 :]
        if x["starts_at"] == y["starts_at"]
    )
    assert client.post("/api/agenda/sessions", json={"session_id": a["id"]}).status_code == 201
    view = client.post("/api/agenda/sessions", json={"session_id": b["id"]}).json()
    assert view["conflicts"] and set(view["conflicts"][0]["session_ids"]) == {a["id"], b["id"]}
    assert client.post("/api/agenda/sessions", json={"session_id": a["id"]}).status_code == 409

    alts = client.get(f"/api/agenda/alternatives/{b['id']}").json()
    assert isinstance(alts, list)
    assert all(x["session"]["id"] not in (a["id"], b["id"]) for x in alts)

    ics = client.get("/api/agenda/export/ics")
    assert ics.status_code == 200 and ics.headers["content-type"].startswith("text/calendar")
    body = ics.text
    assert body.count("BEGIN:VEVENT") == 2 and "TZID=America/Denver" in body
    assert "BEGIN:VTIMEZONE" in body

    assert client.delete(f"/api/agenda/sessions/{b['id']}").json()["conflicts"] == []


def test_assistant_grounding(client):
    r = client.post("/api/assistant/chat", json={"message": "Which talks cover eBPF?"}).json()
    assert r["mode"] == "retrieval_only" and r["sessions"] and r["citations"]
    none = client.post(
        "/api/assistant/chat",
        json={"message": "Are there sessions about medieval pottery glazing techniques?"},
    ).json()
    assert none["mode"] == "no_results" and not none["sessions"]


def test_validation_and_admin_protection(client):
    assert client.get("/api/agenda", headers={"X-Guest-Id": "not-a-uuid"}).status_code == 400
    assert client.post("/api/discovery/search", json={"query": "x" * 600}).status_code == 422
    assert client.get("/api/admin/ingestion/status").status_code == 401
    ok = client.get(
        "/api/admin/ingestion/status", headers={"Authorization": "Bearer test-admin-token"}
    )
    assert ok.status_code == 200 and ok.json()["state"] == "succeeded"


def test_identity_separates_attendees(client):
    r = client.post("/api/identity", json={"handle": "Judge@Example.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "email" and body["display"] == "ju•••@example.com"
    again = client.post("/api/identity", json={"handle": "  judge@example.COM"}).json()
    assert again["attendee_id"] == body["attendee_id"]
    other = client.post("/api/identity", json={"handle": "another_user"}).json()
    assert other["attendee_id"] != body["attendee_id"]
    bad = client.post("/api/identity", json={"handle": "a b"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_handle"

    # Agendas are isolated per identity.
    sid = client.get("/api/sessions", params={"limit": 1}).json()["items"][0]["id"]
    me = {"X-Guest-Id": body["attendee_id"]}
    you = {"X-Guest-Id": other["attendee_id"]}
    add = client.post("/api/agenda/sessions", json={"session_id": sid}, headers=me)
    assert add.status_code == 201
    mine = client.get("/api/agenda", headers=me).json()
    theirs = client.get("/api/agenda", headers=you).json()
    assert mine["total"] == 1 and theirs["total"] == 0

