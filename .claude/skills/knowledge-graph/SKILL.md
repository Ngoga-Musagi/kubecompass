---
name: knowledge-graph
description: Use when extracting entities, adding relationship types, editing the cloud-native vocabulary, changing graph traversal/expansion, or the graph explorer. Enforces provenance and the explicit/extracted/curated/inferred distinction.
---

# Knowledge graph

## When to use
Changes to `app/knowledge_graph/`, `deployment/configuration/vocabulary/cloud-native.yaml`, graph APIs,
or `frontend/app/graph`.

## Scope
Entities: session, speaker, topic, technology, project, organization, track, room.
Relations: PRESENTS, ASSOCIATED_WITH, WORKS_ON, COVERS, USES, DISCUSSES, BELONGS_TO_TRACK,
SCHEDULED_IN, PART_OF, RELATED_TO. Traversal: NetworkX read model (`store.py`) behind `GraphStore`.

## Required inputs
Normalized sessions/speakers; vocabulary YAML; session embeddings for similarity edges.

## Workflow
1. Vocabulary first: add entries with `aliases` (case-insensitive) / `cs_aliases` (acronyms),
   `parents`, `source_tags` (explicit Sessionize tags that map here). Broad topics go in `strict_match`;
   near-universal ones in `low_signal`.
2. Rebuild: `uv run kubecompass ingest`; read `graph` stats in the report.
3. Spot-check extraction: sample sessions and verify each extracted entity's evidence sentence
   actually supports it. Remove or tighten aliases that over-match (e.g. bare "orchestration").
4. Inferred edges: co-occurrence needs count ≥ 3 and lift ≥ 1.5; session RELATED_TO mixes rescaled
   cosine (floor 0.70) with Jaccard over non-low-signal entities.
5. Verify in the UI: `/graph?focus=<entity>` shows evidence for each edge.

## Quality requirements
- Every relationship: `origin`, `method`, `confidence`, and `evidence` (mandatory unless explicit).
- Never upgrade an inferred/extracted edge to explicit; the strongest provenance wins on duplicates.
- Graph views stay legible: neighborhood limits per type, overview keeps ≤ 2 co-occurrence links per node.

## Expected outputs
Updated vocabulary/builder, regenerated graph, stats, and spot-check notes.

## Common mistakes
- Aliases that are common English words ("go", "ray", "spark") without `cs_aliases`.
- Linking organizations from placeholder company values.
- Rendering the whole graph at once.
