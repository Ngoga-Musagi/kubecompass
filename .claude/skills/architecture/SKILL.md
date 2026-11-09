---
name: architecture
description: Use when adding a feature, service, endpoint, data source or conference to KubeCompass, or when a change crosses backend/frontend/Elasticsearch boundaries. Keeps the layered, conference-agnostic architecture intact.
---

# Architecture

## When to use
- New capability that touches more than one layer (ingestion, search, graph, API, UI).
- Adding a conference or a new ingestion adapter.
- Any change to `app/services/container.py`, API contracts, or index mappings.

## Scope & responsibilities
Guard the flow `adapter → canonical model → extraction/graph → ES indices → read model → services → API → UI`
and the rule that conference specifics live in `deployment/configuration/`, never in code.

## Required inputs
The feature request, `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, `docs/API.md`.

## Workflow
1. Locate the layer(s): ingestion (`app/ingestion`), domain (`app/domain/models.py`), graph
   (`app/knowledge_graph`), search (`app/search`), services (`app/recommendation`, `app/agenda`,
   `app/assistant`), API (`app/api`), UI (`frontend/`).
2. Prefer extending an existing service over creating a new one. Wire new services only in
   `app/services/container.py`; routes receive them through `ContainerDep`.
3. New source platform → implement `IngestionAdapter` (`app/ingestion/base.py`), register in
   `ADAPTERS` (`app/ingestion/pipeline.py`), add a conference YAML. No downstream changes.
4. New conference → add `deployment/configuration/conferences/<id>.yaml` (categories, questions,
   format maps, timezone). Run `kubecompass --conference <id> ingest`.
5. Contract change → update `app/schemas/api.py`, `frontend/types/api.ts`, `docs/API.md` together.
6. Index change → edit `elasticsearch/mappings/*.json` (mappings are `dynamic: strict`) and re-ingest;
   aliases swap atomically.
7. Record decisions with real trade-offs in `docs/DECISIONS/NNNN-title.md`.

## Quality requirements
- No KubeCon literals in `app/` (grep `kubecon` should only hit config/tests/docs).
- Every record carries `conference_id` and provenance.
- Services degrade gracefully: ES down → 503 with message; embeddings/LLM down → fallbacks + `degraded`.

## Expected outputs
Code in the right layer, updated contracts/docs, tests, and an ADR when a decision was made.

## Common mistakes
- Querying ES from a route directly instead of via `SearchService`.
- Adding a graph database before NetworkX is a demonstrated bottleneck (see ADR 0003).
- Reading the raw Sessionize payload outside the adapter.
