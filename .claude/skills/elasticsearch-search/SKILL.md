---
name: elasticsearch-search
description: Use when changing mappings, analyzers, queries, hybrid retrieval, RRF, filters, autocomplete or search evaluation in KubeCompass. Elasticsearch is the core search and indexed-data layer.
---

# Elasticsearch search

## When to use
Any change to `elasticsearch/`, `app/search/`, retrieval in recommendations/assistant, or search UX.

## Scope
Indices (aliases): `conference_sessions|speakers|entities|relationships` (versioned per conference),
`conference_attendees`, `conference_changes`. Analysis: `elasticsearch/templates/analysis.json`
(english stemming + search-time synonym_graph).

## Required inputs
Query intent, filters, and the evaluation set `data/evaluation/queries.json`.

## Workflow
1. Mappings are `dynamic: strict`; add fields to the JSON mapping and to `search/indexer.py`.
2. BM25 lives in `bm25_session_query` (title^3, entity_names^2, description, speakers, tags; quoted
   phrases become mandatory `phrase` clauses).
3. kNN uses the `embedding` dense_vector (384-d bge-small, cosine) with the **same bool filter**.
4. Fusion: app-side RRF (`search/fusion.py`, k=60) by default so explanations keep per-retriever ranks;
   `hybrid_native` uses the ES `rrf` retriever (identical ranking, measured faster).
5. Filters come from `SessionFilters` → `session_filter_clauses` → applied to every retriever.
6. After changes: `uv run kubecompass ingest`, `uv run pytest tests/integration -k search`,
   `uv run kubecompass evaluate`, and compare with `docs/SEARCH_DESIGN.md` results.

## Quality requirements
- Semantic similarity must never bypass explicit filters (day, track, format, level, speaker, entity).
- Degrade to BM25 with `degraded: ["vector_unavailable"]` when embeddings are unavailable.
- Report latency and quality honestly; do not claim improvements the evaluation doesn't show.

## Expected outputs
Updated mappings/queries, passing integration tests, refreshed `data/evaluation/results.json`.

## Common mistakes
- Raw bge-small cosine is compressed (median ~0.66 session↔session, on-topic queries ~0.76-0.83,
  off-topic ~0.56-0.62). Rescale before mixing; calibrate thresholds from measurements.
- Facets computed on the current page only (compute over the ranked window).
- Forgetting `is_content` filtering (breaks/logistics should not appear in discovery).
