"""Knowledge-graph queries: overview, neighborhood expansion, entity detail, paths."""

from __future__ import annotations

import itertools
from collections import defaultdict
from typing import Any

from app.knowledge_graph.store import ConferenceReadModel
from app.schemas.api import (
    EntityDetail,
    GraphEdgeOut,
    GraphNodeOut,
    GraphResponse,
    RelatedSession,
)
from app.services.presenters import session_summary, speaker_brief

EXPLORABLE = ("session", "speaker", "topic", "technology", "project", "organization", "track")
_ORIGIN_RANK = {
    "explicit": 0,
    "verified": 1,
    "extracted": 2,
    "curated": 3,
    "ai_extracted": 4,
    "inferred": 5,
}


class UnknownEntityError(KeyError):
    pass


def node_out(rm: ConferenceReadModel, node_id: str) -> GraphNodeOut:
    n = rm.graph.node(node_id) or {}
    meta: dict[str, Any] = {}
    ntype = n.get("type", "unknown")
    if ntype == "session" and node_id in rm.sessions:
        s = rm.sessions[node_id]
        meta = {
            "track": s.get("track"),
            "format": s.get("format"),
            "starts_at_local": (s.get("time") or {}).get("starts_at_local"),
        }
    elif ntype == "speaker" and node_id in rm.speakers:
        sp = rm.speakers[node_id]
        meta = {"company": sp.get("company"), "photo_url": sp.get("photo_url")}
    return GraphNodeOut(
        id=node_id,
        type=ntype,
        name=n.get("name", node_id),
        session_count=n.get("session_count"),
        meta=meta,
    )


def edge_out(data: dict[str, Any]) -> GraphEdgeOut:
    return GraphEdgeOut(
        id=data["id"],
        source=data["source_id"],
        target=data["target_id"],
        type=data["type"],
        origin=data["origin"],
        method=data["method"],
        confidence=data.get("confidence", 1.0),
        evidence=data.get("evidence"),
    )


class GraphService:
    def overview(
        self,
        rm: ConferenceReadModel,
        types: list[str] | None = None,
        per_type: int = 12,
        seeds: list[str] | None = None,
    ) -> GraphResponse:
        """A readable starting graph: the most-covered concepts (or the profile's), and how
        they relate. The full graph is never rendered at once."""
        types = types or ["topic", "technology", "project"]
        chosen: list[str] = []
        if seeds:
            chosen = [s for s in seeds if rm.graph.has_node(s)]
        by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for e in rm.entities.values():
            if e["type"] in types and e.get("session_count", 0) > 0:
                by_type[e["type"]].append(e)
        for t in types:
            ranked = sorted(by_type[t], key=lambda e: -e.get("session_count", 0))
            chosen += [e["id"] for e in ranked[:per_type] if e["id"] not in chosen]
        chosen_set = set(chosen)
        edges: dict[str, GraphEdgeOut] = {}
        # Hierarchy edges always; co-occurrence limited to each node's strongest links so the
        # starting view stays legible.
        for nid in chosen:
            related: list[tuple[float, dict[str, Any]]] = []
            for other, data in rm.graph.neighbors(nid):
                if other not in chosen_set:
                    continue
                if data["type"] == "PART_OF":
                    edges[data["id"]] = edge_out(data)
                elif data["type"] == "RELATED_TO":
                    related.append((float(data.get("weight", 0)), data))
            for _, data in sorted(related, key=lambda x: -x[0])[:2]:
                edges[data["id"]] = edge_out(data)
        return GraphResponse(
            center=None, nodes=[node_out(rm, n) for n in chosen], edges=list(edges.values())
        )

    def neighborhood(
        self,
        rm: ConferenceReadModel,
        node_id: str,
        types: list[str] | None = None,
        limit_per_type: int = 10,
        include_inferred: bool = True,
    ) -> GraphResponse:
        if not rm.graph.has_node(node_id):
            raise UnknownEntityError(node_id)
        allowed = set(types or EXPLORABLE)
        groups: dict[str, list[tuple[float, str, dict[str, Any]]]] = defaultdict(list)
        for other, data in rm.graph.neighbors(node_id):
            node = rm.graph.node(other) or {}
            ntype = node.get("type")
            if ntype not in allowed or ntype == "room":
                continue
            if not include_inferred and data["origin"] == "inferred":
                continue
            if ntype == "session" and not node.get("is_content", True):
                continue
            score = data.get("confidence", 1.0) * (
                1 + min(float(data.get("weight", 1.0)), 3.0)
            ) - 0.05 * _ORIGIN_RANK.get(data["origin"], 5)
            if ntype in ("topic", "technology", "project"):
                score += 0.002 * min(node.get("session_count", 0) or 0, 100)
            groups[ntype].append((score, other, data))
        nodes = [node_out(rm, node_id)]
        edges: dict[str, GraphEdgeOut] = {}
        truncated: dict[str, int] = {}
        kept: set[str] = {node_id}
        for ntype, items in groups.items():
            best: dict[str, tuple[float, dict[str, Any]]] = {}
            for score, other, data in items:
                if other not in best or score > best[other][0]:
                    best[other] = (score, data)
            ranked = sorted(best.items(), key=lambda kv: -kv[1][0])
            if len(ranked) > limit_per_type:
                truncated[ntype] = len(ranked) - limit_per_type
            for other, (_, data) in ranked[:limit_per_type]:
                kept.add(other)
                nodes.append(node_out(rm, other))
                edges[data["id"]] = edge_out(data)
        # Structure between kept concept nodes (helps the layout tell a story).
        for nid in kept:
            if nid == node_id:
                continue
            for other, data in rm.graph.neighbors(nid):
                if (
                    other in kept
                    and other != node_id
                    and data["type"] == "PART_OF"
                    and (rm.graph.node(nid) or {}).get("type") != "session"
                ):
                    edges.setdefault(data["id"], edge_out(data))
        return GraphResponse(
            center=node_id, nodes=nodes, edges=list(edges.values()), truncated=truncated
        )

    def entity_detail(
        self, rm: ConferenceReadModel, entity_id: str, limit: int = 40
    ) -> EntityDetail:
        node = rm.graph.node(entity_id)
        if node is None or node.get("type") in ("session", "speaker"):
            raise UnknownEntityError(entity_id)
        sessions: dict[str, RelatedSession] = {}
        speakers: dict[str, Any] = {}
        related: dict[str, GraphNodeOut] = {}
        parents: dict[str, GraphNodeOut] = {}
        children: dict[str, GraphNodeOut] = {}
        for other, data in rm.graph.neighbors(entity_id):
            otype = (rm.graph.node(other) or {}).get("type")
            if otype == "session" and other in rm.sessions:
                prev = sessions.get(other)
                if prev is None or _ORIGIN_RANK[data["origin"]] < _ORIGIN_RANK[prev.origin]:
                    sessions[other] = RelatedSession(
                        session=session_summary(rm.sessions[other], rm.speakers),
                        evidence=data.get("evidence"),
                        confidence=data.get("confidence", 1.0),
                        origin=data["origin"],
                    )
            elif otype == "speaker" and other in rm.speakers:
                speakers[other] = rm.speakers[other]
            elif data["type"] == "PART_OF":
                (children if data["direction"] == "in" else parents)[other] = node_out(rm, other)
            elif data["type"] == "RELATED_TO":
                related[other] = node_out(rm, other)
        ordered = sorted(
            sessions.values(),
            key=lambda r: (
                not r.session.is_content,
                _ORIGIN_RANK[r.origin],
                -r.confidence,
                r.session.starts_at_local or "",
            ),
        )
        # Organizations reach sessions through their speakers.
        if node.get("type") == "organization":
            for sp_id in speakers:
                for sid in rm.speakers[sp_id].get("session_ids", []):
                    if sid in rm.sessions and sid not in sessions:
                        ordered.append(
                            RelatedSession(
                                session=session_summary(rm.sessions[sid], rm.speakers),
                                evidence=f"Presented by {rm.speakers[sp_id]['full_name']}",
                                confidence=1.0,
                                origin="explicit",
                            )
                        )
        return EntityDetail(
            entity=node_out(rm, entity_id),
            origin=rm.entities.get(entity_id, {}).get("origin", "explicit"),
            sessions=ordered[:limit],
            speakers=[speaker_brief(s) for s in speakers.values()][:limit],
            related=sorted(related.values(), key=lambda n: -(n.session_count or 0))[:16],
            parents=list(parents.values()),
            children=list(children.values()),
        )

    def related_sessions(
        self, rm: ConferenceReadModel, session_id: str, limit: int = 6
    ) -> list[RelatedSession]:
        out: list[tuple[float, RelatedSession]] = []
        seen: set[str] = set()
        for other, data in rm.graph.neighbors(session_id):
            if data["type"] != "RELATED_TO" or other not in rm.sessions or other in seen:
                continue
            seen.add(other)
            out.append(
                (
                    float(data.get("weight", 0)),
                    RelatedSession(
                        session=session_summary(rm.sessions[other], rm.speakers),
                        evidence=data.get("evidence"),
                        confidence=data.get("confidence", 0.0),
                        origin=data["origin"],
                    ),
                )
            )
        return [r for _, r in sorted(out, key=lambda x: -x[0])][:limit]

    def path(self, rm: ConferenceReadModel, a: str, b: str) -> GraphResponse:
        nodes = rm.graph.shortest_path(a, b)
        if not nodes:
            return GraphResponse(center=a, nodes=[], edges=[])
        edges: list[GraphEdgeOut] = []
        for u, v in itertools.pairwise(nodes):
            cands = [d for o, d in rm.graph.neighbors(u) if o == v]
            if cands:
                best = min(cands, key=lambda d: _ORIGIN_RANK.get(d["origin"], 5))
                edges.append(edge_out(best))
        return GraphResponse(center=a, nodes=[node_out(rm, n) for n in nodes], edges=edges)
