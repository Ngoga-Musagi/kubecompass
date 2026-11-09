"""Elasticsearch client factory and index naming."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from elasticsearch import ApiError, Elasticsearch, TransportError

from app.config.settings import Settings, get_settings

log = logging.getLogger(__name__)

INDEX_KINDS = ("sessions", "speakers", "entities", "relationships")
STATE_KINDS = ("attendees", "changes")


class SearchUnavailableError(RuntimeError):
    """Elasticsearch is unreachable or returned an unexpected error."""


def alias(kind: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return f"{settings.es_index_prefix}_{kind}"


def physical_index(kind: str, conference_id: str, version: str) -> str:
    safe = version.lower().replace(":", "").replace("+", "-").replace(".", "-")
    return f"{alias(kind)}__{conference_id}__{safe}"


def load_mapping(kind: str) -> dict[str, Any]:
    root = get_settings().repo_root / "elasticsearch"
    return json.loads((root / "mappings" / f"{kind}.json").read_text(encoding="utf-8"))


def load_analysis() -> dict[str, Any]:
    root: Path = get_settings().repo_root / "elasticsearch"
    return json.loads((root / "templates" / "analysis.json").read_text(encoding="utf-8"))


@lru_cache
def is_serverless() -> bool:
    """Elastic Cloud Serverless rejects shard/replica settings and some cluster APIs."""
    try:
        info = get_es().info()
        return info.get("version", {}).get("build_flavor") == "serverless"
    except Exception:
        return False


def index_body(kind: str, dims: int | None = None) -> dict[str, Any]:
    mapping = load_mapping(kind)
    if dims is not None and "embedding" in mapping["properties"]:
        mapping["properties"]["embedding"]["dims"] = dims
    sem = get_settings().semantic_text_inference_id
    if sem and kind in ("sessions", "speakers"):
        # Native semantic field (e.g. Jina on EIS) for Agent Builder / Workflows `semantic` queries.
        mapping["properties"]["semantic_content"] = {"type": "semantic_text", "inference_id": sem}
    settings: dict[str, Any] = dict(load_analysis())
    if not is_serverless():
        settings.update({"number_of_shards": 1, "number_of_replicas": 0})
    return {"settings": settings, "mappings": mapping}


@lru_cache
def get_es() -> Elasticsearch:
    s = get_settings()
    kwargs: dict[str, Any] = {
        "request_timeout": s.es_timeout_seconds,
        "retry_on_timeout": True,
        "max_retries": 2,
    }
    if s.es_api_key:
        kwargs["api_key"] = s.es_api_key.get_secret_value()
    return Elasticsearch(s.es_url, **kwargs)


def es_call(fn, *args, **kwargs):  # type: ignore[no-untyped-def]
    """Run an ES call, translating transport/API failures into SearchUnavailableError."""
    try:
        return fn(*args, **kwargs)
    except (TransportError, ApiError) as exc:
        log.warning("Elasticsearch call failed: %s", exc)
        raise SearchUnavailableError(str(exc)) from exc


def ensure_state_indices(es: Elasticsearch) -> None:
    for kind in STATE_KINDS:
        name = alias(kind)
        if not es.indices.exists(index=name):
            es.indices.create(index=name, **index_body(kind))
