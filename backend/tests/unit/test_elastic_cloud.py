"""Elastic Cloud integration pieces (no network): assets, idempotent setup, Serverless index
settings, Jina inference embeddings and the Agent Builder LLM provider."""

from __future__ import annotations

import json
from typing import Any

import httpx
import numpy as np
import pytest
import yaml
from pydantic import BaseModel, SecretStr

from app.config.settings import get_settings
from app.elastic import setup as elastic
from app.infrastructure import elasticsearch as es_mod
from app.infrastructure.embeddings import ElasticInferenceEmbeddingProvider
from app.infrastructure.llm import ElasticAgentProvider, LLMUnavailableError


@pytest.fixture
def cloud_settings():
    return get_settings().model_copy(
        update={
            "kibana_url": "https://kb.example.elastic.cloud",
            "es_api_key": SecretStr("test-key"),
        }
    )


def test_assets_are_consistent():
    assets = elastic.load_assets(get_settings().repo_root)
    tool_ids = {t["id"] for t in assets.tools}
    assert {"kubecompass_search_sessions", "kubecompass_topic_briefing"} <= tool_ids
    for tool in assets.tools:
        assert tool["type"] in {"esql", "index_search", "workflow"}
        if tool["type"] == "esql":
            for name, spec in tool["configuration"].get("params", {}).items():
                assert f"?{name}" in tool["configuration"]["query"]
                # Allowed by Agent Builder (verified against Kibana 9.4.8)
                assert spec["type"] in {"string", "integer", "float", "boolean", "date", "array"}
        if tool["type"] == "workflow":
            assert tool["configuration"]["workflow_id"] in assets.workflows
    for agent in assets.agents:
        for group in agent["configuration"]["tools"]:
            for tid in group["tool_ids"]:
                assert tid in tool_ids or tid.startswith("platform.core.")
    for wid, text in assets.workflows.items():
        wf = yaml.safe_load(text)
        assert wf["name"] and wf["triggers"] and wf["steps"], wid
        for step in wf["steps"]:
            if step["type"] == "ai.agent":
                assert step["agent-id"] in {a["id"] for a in assets.agents}


def _walk(node, path=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, (*path, k))
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v, path)
    else:
        yield path, node


def test_workflow_term_queries_avoid_boolean_values():
    """Kibana 9.4.8's workflow validator marks a workflow invalid when a `term` query has a
    YAML boolean value (found by bisection against a real Kibana); use the string "true"."""
    for wid, text in elastic.load_assets(get_settings().repo_root).workflows.items():
        for path, value in _walk(yaml.safe_load(text)):
            if "term" in path:
                assert not isinstance(value, bool), (wid, path)
            if path[-2:] == ("rrule", "freq"):
                assert value in {"DAILY", "WEEKLY"}, (wid, value)  # HOURLY rejected (9.4.8)


class FakeKibana:
    """In-memory Kibana implementing the endpoints setup() uses."""

    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        self.calls.append((method, path))
        assert request.headers["kbn-xsrf"] == "true"
        assert request.headers["Authorization"] == "ApiKey test-key"
        body = json.loads(request.content) if request.content else None
        if method == "GET":
            return (
                httpx.Response(200, json=self.objects[path])
                if path in self.objects
                else httpx.Response(404, json={"message": "not found"})
            )
        if method == "POST":
            self.objects[f"{path}/{body['id']}"] = body
            return httpx.Response(200, json=body)
        if method == "PUT":
            assert "id" not in body
            self.objects[path].update(body)
            return httpx.Response(200, json=self.objects[path])
        return httpx.Response(405)


def test_setup_is_idempotent_and_ordered(cloud_settings):
    fake = FakeKibana()
    first = elastic.setup(cloud_settings, transport=httpx.MockTransport(fake))
    assert first.ok and all(line.endswith("created") for line in first.done)
    posts = [p for m, p in fake.calls if m == "POST"]
    assert posts.index("/api/workflows/workflow") < posts.index("/api/agent_builder/tools")
    assert posts[-1] == "/api/agent_builder/agents"
    second = elastic.setup(cloud_settings, transport=httpx.MockTransport(fake))
    assert second.ok and all(line.endswith("updated") for line in second.done)


def test_setup_survives_failing_workflows(cloud_settings):
    fake = FakeKibana()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/workflows"):
            return httpx.Response(403, json={"message": "Workflows not enabled"})
        return fake(request)

    report = elastic.setup(cloud_settings, transport=httpx.MockTransport(handler))
    assert any("workflow" in f for f in report.failed)
    guide = fake.objects["/api/agent_builder/agents/kubecompass-guide"]
    tools = guide["configuration"]["tools"][0]["tool_ids"]
    assert "kubecompass_topic_briefing" not in tools and "kubecompass_search_sessions" in tools


def test_serverless_index_body_omits_shard_settings(monkeypatch):
    monkeypatch.setattr(es_mod, "is_serverless", lambda: True)
    body = es_mod.index_body("sessions", dims=1024)
    assert "number_of_shards" not in body["settings"]
    assert body["mappings"]["properties"]["embedding"]["dims"] == 1024
    monkeypatch.setattr(es_mod, "is_serverless", lambda: False)
    assert es_mod.index_body("sessions")["settings"]["number_of_shards"] == 1


def test_semantic_text_field_when_configured(monkeypatch):
    monkeypatch.setattr(es_mod, "is_serverless", lambda: True)
    s = get_settings().model_copy(update={"semantic_text_inference_id": ".jina-embeddings-v3"})
    monkeypatch.setattr(es_mod, "get_settings", lambda: s)
    props = es_mod.index_body("sessions")["mappings"]["properties"]
    assert props["semantic_content"] == {
        "type": "semantic_text",
        "inference_id": ".jina-embeddings-v3",
    }


def test_jina_inference_embeddings_batched_and_normalized():
    class FakeInference:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def inference(self, **kw):
            self.calls.append(kw)
            return {"text_embedding": [{"embedding": [3.0, 4.0]} for _ in kw["input"]]}

    p = ElasticInferenceEmbeddingProvider.__new__(ElasticInferenceEmbeddingProvider)
    fake = FakeInference()
    p.es = type("ES", (), {"inference": fake})()
    p.inference_id, p.dimensions, p._query_cache = ".jina-embeddings-v3", 2, {}
    vecs = p.embed_passages([f"t{i}" for i in range(40)])
    assert vecs.shape == (40, 2) and np.allclose(vecs[0], [0.6, 0.8])
    assert [len(c["input"]) for c in fake.calls] == [16, 16, 8]
    assert {c["input_type"] for c in fake.calls} == {"ingest"}
    p.embed_query("q")
    p.embed_query("q")  # cached
    assert fake.calls[-1]["input_type"] == "search" and len(fake.calls) == 4


class Out(BaseModel):
    topics: list[str]


def test_elastic_agent_provider(cloud_settings):
    replies = iter(
        [
            {"response": {"message": "Answer [S1]"}},
            {"response": {"message": 'Sure! {"topics": ["eBPF"]} hope this helps'}},
            {"response": {"message": "not json"}},
        ]
    )
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=next(replies))

    p = ElasticAgentProvider(cloud_settings)
    p._kb._http = httpx.Client(base_url="https://kb", transport=httpx.MockTransport(handler))
    assert p.complete("sys", "user").text == "Answer [S1]"
    assert seen[0]["agent_id"] == "kubecompass-llm"
    assert p.structured("sys", "user", Out).topics == ["eBPF"]
    with pytest.raises(LLMUnavailableError):
        p.structured("sys", "user", Out)


def test_calibration_is_model_specific():
    from app.infrastructure.calibration import calibration_for

    bge = calibration_for("BAAI/bge-small-en-v1.5")
    jina = calibration_for("elastic:.jina-embeddings-v3")
    assert jina.coverage_min < bge.coverage_min  # Jina scores live on a lower, wider scale
    assert calibration_for("some-unknown-model") == bge  # default entry
    for c in (bge, jina):
        assert c.query_floor < c.query_ceiling and c.related_floor < c.related_ceiling
