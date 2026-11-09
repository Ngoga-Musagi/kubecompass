# Architecture

```
            ┌──────────── deployment/configuration ────────────┐
            │ conferences/*.yaml · vocabulary · ranking.yaml   │
            └───────────────────────┬──────────────────────────┘
Sessionize ──► IngestionAdapter ──► canonical model ──► vocabulary extraction + graph builder
 (local/live)  (validate, normalize,  (Session, Speaker,   (explicit / extracted / curated /
               dedupe, provenance)     Entity, Relationship) inferred edges with evidence)
                                              │
                         FastEmbed (bge-small, local) ── embeddings (content-addressed cache)
                                              │
                            Elasticsearch: versioned per-conference indices behind aliases
            conference_sessions · _speakers · _entities · _relationships · _attendees · _changes
                                              │
              FastAPI ── ReadModelRegistry (NetworkX graph + vectors, reloaded on alias change)
               │  SearchService (BM25 · kNN · RRF app/native · filters · facets · autocomplete)
               │  GraphService (overview · neighborhood · entity · path · related)
               │  RecommendationService (profile → retrieval → PPR → scoring → tiers → explain)
               │  AgendaService + ICS · AssistantService (RAG; Claude optional)
               ▼
        Next.js 15 UI (React Query, Tailwind v4 tokens, Radix, Cytoscape)
```

## Components
| Component | Path | Notes |
|---|---|---|
| Config | `backend/app/config/` | env settings (`KUBECOMPASS_*`), conference YAML loader |
| Domain | `backend/app/domain/models.py` | canonical, conference-agnostic Pydantic models |
| Ingestion | `backend/app/ingestion/` | adapter protocol, Sessionize adapter, pipeline, snapshot store, diff |
| Graph | `backend/app/knowledge_graph/` | vocabulary, extractor, builder, `GraphStore` (NetworkX), service |
| Search | `backend/app/search/` | filters, RRF, query builders, indexer (alias swap) |
| Recommendation | `backend/app/recommendation/` | profile + parsers, scoring, explanations, service |
| Agenda | `backend/app/agenda/`, `app/calendar/` | ES-backed attendee store, scheduling, ICS |
| Assistant | `backend/app/assistant/` | intent routing, retrieval, grounded generation |
| API | `backend/app/api/` | routes, deps (guest id, admin token, rate limit) |
| Wiring | `backend/app/services/container.py` | single dependency graph |
| UI | `frontend/` | pages in `app/`, components by domain |

## Key flows
**Ingestion** (`kubecompass ingest [--remote]`): load → schema validation → plausibility checks
(≥ 10 sessions, ≤ 30% drop) → normalize → extract entities → embed → build graph → diff vs last
snapshot → index into new versioned indices → atomic alias swap → save snapshot + status. Any
failure leaves the previous indices and snapshot serving (see ADR 0004).

**Read model**: on first request (and at startup) the API loads sessions, speakers, entities,
relationships and vectors for a conference from Elasticsearch into memory; it re-checks the alias
version every 15 s, so refreshes appear without restarts.

**Recommendation**: see `RECOMMENDATION_ENGINE.md`. **Search**: see `SEARCH_DESIGN.md`.

## Reliability & security
- ES unavailable → 503 `search_unavailable`; embeddings unavailable → BM25 with `degraded`;
  LLM unavailable → rule parser / extractive assistant.
- Admin endpoints require `KUBECOMPASS_ADMIN_TOKEN` (constant-time compare); disabled if unset.
- Guest identity is a client UUID (`X-Guest-Id`), validated; no personal data collected.
- Inputs validated by Pydantic (lengths, ranges, patterns); errors never expose internals.
- In-memory per-IP rate limit on LLM-capable endpoints (`intent`, `recommendations`, `assistant`).
- CORS restricted to configured origins; ES bound to 127.0.0.1 in Compose; security disabled
  for the local demo only (enable xpack security + API key for any shared deployment).
- External services: Sessionize (public read), Hugging Face (one-time model download),
  Anthropic / OpenAI APIs and local Ollama (all optional, chained with failover). Only attendee query text and public conference records go to the LLM.

## Deployment
`docker compose up -d --build` runs ES 9.4.8, the backend (auto-ingests if the index is missing via
`kubecompass ensure`) and the Next.js standalone frontend. See README.
