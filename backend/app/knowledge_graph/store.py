"""In-memory conference read model loaded from Elasticsearch.

Holds the NetworkX graph, lightweight session/speaker records and session
vectors. It is rebuilt when the indices behind the read aliases change, so the
graph is always consistent with what search serves. The `GraphStore` protocol
keeps NetworkX replaceable (e.g. by a graph database) without touching callers.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import networkx as nx
import numpy as np
from elasticsearch import Elasticsearch, helpers

from app.infrastructure.elasticsearch import alias, es_call

log = logging.getLogger(__name__)


class GraphStore(Protocol):
    def neighbors(self, node_id: str) -> list[tuple[str, dict[str, Any]]]: ...

    def node(self, node_id: str) -> dict[str, Any] | None: ...

    def has_node(self, node_id: str) -> bool: ...

    def personalized_pagerank(self, seeds: dict[str, float]) -> dict[str, float]: ...

    def shortest_path(self, a: str, b: str, max_len: int = 4) -> list[str] | None: ...


class NetworkXGraphStore:
    def __init__(self, graph: nx.MultiDiGraph) -> None:
        self.g = graph
        # Undirected weighted projection for traversal / ranking.
        self.ug = nx.Graph()
        for u, v, data in graph.edges(data=True):
            if data.get("type") == "SCHEDULED_IN":
                continue
            w = float(data.get("confidence", 1.0)) * float(min(data.get("weight", 1.0), 3.0))
            if self.ug.has_edge(u, v):
                self.ug[u][v]["weight"] = max(self.ug[u][v]["weight"], w)
            else:
                self.ug.add_edge(u, v, weight=w)

    def neighbors(self, node_id: str) -> list[tuple[str, dict[str, Any]]]:
        out: list[tuple[str, dict[str, Any]]] = []
        if node_id not in self.g:
            return out
        for _, v, data in self.g.out_edges(node_id, data=True):
            out.append((v, {**data, "direction": "out"}))
        for u, _, data in self.g.in_edges(node_id, data=True):
            out.append((u, {**data, "direction": "in"}))
        return out

    def node(self, node_id: str) -> dict[str, Any] | None:
        return dict(self.g.nodes[node_id]) if node_id in self.g else None

    def has_node(self, node_id: str) -> bool:
        return node_id in self.g

    def personalized_pagerank(self, seeds: dict[str, float]) -> dict[str, float]:
        valid = {k: v for k, v in seeds.items() if k in self.ug and v > 0}
        if not valid:
            return {}
        return nx.pagerank(
            self.ug, alpha=0.75, personalization=valid, weight="weight", max_iter=200, tol=1e-6
        )

    def shortest_path(self, a: str, b: str, max_len: int = 4) -> list[str] | None:
        if a not in self.ug or b not in self.ug:
            return None
        try:
            path = nx.shortest_path(self.ug, a, b)
        except nx.NetworkXNoPath:
            return None
        return path if len(path) - 1 <= max_len else None


@dataclass
class ConferenceReadModel:
    conference_id: str
    version: str
    graph: GraphStore
    sessions: dict[str, dict[str, Any]]  # id -> canonical session doc
    speakers: dict[str, dict[str, Any]]
    entities: dict[str, dict[str, Any]]
    vector_ids: list[str] = field(default_factory=list)
    vectors: np.ndarray | None = None
    _vec_index: dict[str, int] = field(default_factory=dict)

    def vector(self, session_id: str) -> np.ndarray | None:
        if self.vectors is None or session_id not in self._vec_index:
            return None
        return self.vectors[self._vec_index[session_id]]


def current_version(es: Elasticsearch, conference_id: str) -> str | None:
    try:
        resp = es.indices.get_alias(name=alias("sessions"))
    except Exception:
        return None
    names = sorted(n for n in resp if f"__{conference_id}__" in n)
    return names[-1].rsplit("__", 1)[-1] if names else None


def load_read_model(es: Elasticsearch, conference_id: str) -> ConferenceReadModel | None:
    version = current_version(es, conference_id)
    if version is None:
        return None
    cflt = {"term": {"conference_id": conference_id}}
    sessions: dict[str, dict[str, Any]] = {}
    vec_ids: list[str] = []
    vecs: list[list[float]] = []
    for h in helpers.scan(
        es, index=alias("sessions"), query={"query": cflt}, _source=["doc", "embedding"]
    ):
        sessions[h["_id"]] = h["_source"]["doc"]
        if "embedding" in h["_source"]:
            vec_ids.append(h["_id"])
            vecs.append(h["_source"]["embedding"])
    speakers = {
        h["_id"]: h["_source"]["doc"]
        for h in helpers.scan(es, index=alias("speakers"), query={"query": cflt}, _source=["doc"])
    }
    entities = {
        h["_id"]: h["_source"]
        for h in helpers.scan(es, index=alias("entities"), query={"query": cflt})
    }

    g = nx.MultiDiGraph()
    for sid, s in sessions.items():
        g.add_node(sid, type="session", name=s["title"], is_content=s.get("is_content", True))
    for pid, p in speakers.items():
        g.add_node(pid, type="speaker", name=p["full_name"])
    for eid, e in entities.items():
        g.add_node(eid, type=e["type"], name=e["name"], session_count=e.get("session_count", 0))
    edge_count = 0
    for h in helpers.scan(es, index=alias("relationships"), query={"query": cflt}):
        r = h["_source"]
        if r["source_id"] in g and r["target_id"] in g:
            g.add_edge(r["source_id"], r["target_id"], key=r["type"], **r)
            edge_count += 1
    matrix = np.array(vecs, dtype=np.float32) if vecs else None
    log.info(
        "Loaded read model %s@%s: %d nodes, %d edges, %d vectors",
        conference_id,
        version,
        g.number_of_nodes(),
        edge_count,
        len(vec_ids),
    )
    return ConferenceReadModel(
        conference_id=conference_id,
        version=version,
        graph=NetworkXGraphStore(g),
        sessions=sessions,
        speakers=speakers,
        entities=entities,
        vector_ids=vec_ids,
        vectors=matrix,
        _vec_index={sid: i for i, sid in enumerate(vec_ids)},
    )


class ReadModelRegistry:
    """Caches one read model per conference; reloads when the indexed version changes."""

    def __init__(self, es: Elasticsearch, check_interval_s: float = 15.0) -> None:
        self.es = es
        self._models: dict[str, ConferenceReadModel] = {}
        self._checked: dict[str, float] = {}
        self._interval = check_interval_s
        self._lock = threading.Lock()

    def get(self, conference_id: str) -> ConferenceReadModel | None:
        model = self._models.get(conference_id)
        now = time.monotonic()
        if model is not None and now - self._checked.get(conference_id, 0) < self._interval:
            return model
        current = es_call(current_version, self.es, conference_id)
        self._checked[conference_id] = now
        if model is not None and model.version == current:
            return model
        with self._lock:
            model = self._models.get(conference_id)
            if model is None or model.version != current:
                loaded = es_call(load_read_model, self.es, conference_id)
                if loaded is not None:
                    self._models[conference_id] = loaded
                model = self._models.get(conference_id)
        return model

    def invalidate(self, conference_id: str) -> None:
        self._models.pop(conference_id, None)
        self._checked.pop(conference_id, None)
