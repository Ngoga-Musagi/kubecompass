"""Provision KubeCompass on Elastic: Agent Builder tools + agents and Elastic Workflows.

Definitions live in `elasticsearch/agent-builder/{tools,agents}/*.json` and
`elasticsearch/workflows/*.yaml`. Every operation is idempotent (create or update).
Order matters: workflows → tools (a workflow tool references a workflow) → agents.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config.settings import Settings
from app.elastic.kibana import KibanaClient, KibanaError

TOOLS = "/api/agent_builder/tools"
AGENTS = "/api/agent_builder/agents"
WORKFLOWS = "/api/workflows/workflow"


@dataclass
class Assets:
    workflows: dict[str, str]  # id -> yaml
    tools: list[dict[str, Any]]
    agents: list[dict[str, Any]]


@dataclass
class Report:
    done: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


def load_assets(repo_root: Path) -> Assets:
    root = repo_root / "elasticsearch"
    return Assets(
        workflows={
            p.stem: p.read_text(encoding="utf-8")
            for p in sorted((root / "workflows").glob("*.yaml"))
        },
        tools=[
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((root / "agent-builder" / "tools").glob("*.json"))
        ],
        agents=[
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((root / "agent-builder" / "agents").glob("*.json"))
        ],
    )


def _upsert_workflow(kb: KibanaClient, wid: str, yaml: str) -> str:
    if kb.request("GET", f"{WORKFLOWS}/{wid}", allow_404=True) is None:
        kb.request("POST", WORKFLOWS, {"id": wid, "yaml": yaml})
        return "created"
    kb.request("PUT", f"{WORKFLOWS}/{wid}", {"yaml": yaml})
    return "updated"


def _upsert(kb: KibanaClient, base: str, body: dict[str, Any], immutable: tuple[str, ...]) -> str:
    oid = body["id"]
    if kb.request("GET", f"{base}/{oid}", allow_404=True) is None:
        kb.request("POST", base, body)
        return "created"
    kb.request("PUT", f"{base}/{oid}", {k: v for k, v in body.items() if k not in immutable})
    return "updated"


def setup(settings: Settings, *, skip_workflows: bool = False, transport: Any = None) -> Report:
    assets = load_assets(settings.repo_root)
    report = Report()
    kb = KibanaClient(settings, transport=transport)
    try:
        failed_workflows: set[str] = set()
        if not skip_workflows:
            for wid, yaml in assets.workflows.items():
                try:
                    report.done.append(f"workflow {wid}: {_upsert_workflow(kb, wid, yaml)}")
                except KibanaError as exc:
                    failed_workflows.add(wid)
                    report.failed.append(f"workflow {wid}: {exc}")
        created_tools: set[str] = set()
        for tool in assets.tools:
            wid = tool.get("configuration", {}).get("workflow_id")
            if tool["type"] == "workflow" and (skip_workflows or wid in failed_workflows):
                report.failed.append(f"tool {tool['id']}: skipped (workflow {wid} unavailable)")
                continue
            try:
                result = _upsert(kb, TOOLS, tool, immutable=("id", "type"))
                created_tools.add(tool["id"])
                report.done.append(f"tool {tool['id']}: {result}")
            except KibanaError as exc:
                report.failed.append(f"tool {tool['id']}: {exc}")
        known = {t["id"] for t in assets.tools}
        for agent in assets.agents:
            body = json.loads(json.dumps(agent))
            # Drop references to our own tools that failed, so the agent still gets created.
            for group in body["configuration"].get("tools", []):
                group["tool_ids"] = [
                    t for t in group["tool_ids"] if t not in known or t in created_tools
                ]
            try:
                report.done.append(
                    f"agent {agent['id']}: {_upsert(kb, AGENTS, body, immutable=('id',))}"
                )
            except KibanaError as exc:
                report.failed.append(f"agent {agent['id']}: {exc}")
    finally:
        kb.close()
    return report


def teardown(settings: Settings) -> Report:
    assets = load_assets(settings.repo_root)
    report = Report()
    kb = KibanaClient(settings)
    try:
        targets = (
            [(AGENTS, a["id"]) for a in assets.agents]
            + [(TOOLS, t["id"]) for t in assets.tools]
            + [(WORKFLOWS, w) for w in assets.workflows]
        )
        for base, oid in targets:
            try:
                gone = kb.request("DELETE", f"{base}/{oid}", allow_404=True) is None
                report.done.append(
                    f"{base.rsplit('/', 1)[-1]} {oid}: {'absent' if gone else 'deleted'}"
                )
            except KibanaError as exc:
                report.failed.append(f"{oid}: {exc}")
    finally:
        kb.close()
    return report


APP_KEY_ROLE: dict[str, Any] = {
    "kubecompass_public_app": {
        # monitor: GET / for health; monitor_inference: call the Jina inference endpoint.
        "cluster": ["monitor", "monitor_inference"],
        "indices": [
            {
                "names": [
                    "conference_sessions*",
                    "conference_speakers*",
                    "conference_entities*",
                    "conference_relationships*",
                    "conference_changes*",
                ],
                "privileges": ["read", "view_index_metadata"],
            },
            {
                "names": ["conference_attendees*"],
                "privileges": ["read", "write", "view_index_metadata"],
            },
        ],
    }
}


def create_app_key(name: str, expiration: str | None = None) -> str:
    """Least-privilege API key for a public deployment: read conference data, write only attendee
    agendas/profiles, call inference. Cannot ingest, delete, or use Kibana."""
    from app.infrastructure.elasticsearch import get_es

    body: dict[str, Any] = {
        "name": name,
        "role_descriptors": APP_KEY_ROLE,
        "metadata": {"application": "kubecompass", "purpose": "public-app"},
    }
    if expiration:
        body["expiration"] = expiration
    return str(get_es().security.create_api_key(**body)["encoded"])


def check(settings: Settings) -> list[tuple[str, bool, str]]:
    """Connectivity and capability checks for the active profile."""
    from app.infrastructure.elasticsearch import get_es

    results: list[tuple[str, bool, str]] = []
    try:
        info = get_es().info()
        flavor = info.get("version", {}).get("build_flavor", "default")
        results.append(
            ("Elasticsearch", True, f"{settings.es_url} | {info['version']['number']} | {flavor}")
        )
    except Exception as exc:
        results.append(("Elasticsearch", False, str(exc)[:200]))
        return results
    try:
        eps = get_es().inference.get(inference_id="_all").get("endpoints", [])
        ids = {e["inference_id"] for e in eps}
        for needed in {
            settings.elastic_embedding_inference_id
            if settings.embedding_provider == "elastic"
            else "",
            settings.semantic_text_inference_id,
        } - {""}:
            results.append(
                (
                    f"Inference {needed}",
                    needed in ids,
                    "available" if needed in ids else f"not found ({len(ids)} endpoints exist)",
                )
            )
    except Exception as exc:
        results.append(("Inference API", False, str(exc)[:200]))
    if settings.kibana_url:
        kb = KibanaClient(settings, timeout=15)
        try:
            for name, path in (("Agent Builder", TOOLS), ("Workflows", "/api/workflows")):
                try:
                    kb.request("GET", path)
                    results.append((name, True, "reachable"))
                except KibanaError as exc:
                    results.append((name, False, str(exc)))
        finally:
            kb.close()
    else:
        results.append(("Kibana", False, "KUBECOMPASS_KIBANA_URL not set"))
    return results
