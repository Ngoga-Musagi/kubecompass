# API

Base: `http://localhost:8000`. OpenAPI: `/docs`. All endpoints accept `?conference=<id>`
(default from settings). Attendee endpoints require `X-Guest-Id: <uuid>`: either a random
per-tab id, or the personal id from `POST /api/identity`.
Errors: `{"error": {"code": "...", "message": "..."}}` with 400/401/403/404/409/422/429/503.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | ES, embeddings, LLM status; indexed conferences |
| GET | `/api/conferences` · `/api/conferences/{id}` | metadata, days, tracks/formats with counts, data version, last refresh |
| GET | `/api/sessions` | browse; `day, track, format, level, entity` (repeatable), `offset, limit` |
| GET | `/api/sessions/{id}` | detail: abstract, entities with origin/evidence, resources, provenance, related |
| GET | `/api/sessions/{id}/alternatives` | similar sessions (fitting the guest's agenda first) |
| GET | `/api/speakers` | hybrid speaker search `q`, `entity`, paging |
| GET | `/api/speakers/{id}` | bio, sessions, works-on (with origin), co-presenters |
| POST | `/api/discovery/intent` | `{text, save}` → `InterestProfile` (rules or LLM, grounded) |
| POST | `/api/identity` | `{handle}` (email or username) → `{attendee_id, kind, display}`: a stable HMAC-derived id; the handle is never stored (rate-limited) |
| GET / PUT | `/api/profile` | read / replace the guest's profile |
| POST | `/api/discovery/search` | `{query, filters, mode: keyword|vector|hybrid|hybrid_native, offset, limit}` → hits with BM25/vector ranks, highlights, facets, `degraded` |
| GET | `/api/discovery/suggest?q=` | autocomplete: sessions, speakers, entities |
| GET | `/api/discovery/pathways` | data-derived topic pathways (profile matches first) |
| POST | `/api/recommendations` | `{profile?, filters}` → tiers, components, explanations, insights, pipeline stats |
| GET | `/api/knowledge-graph` | overview (`types`, `per_type`, `personalized`) |
| GET | `/api/knowledge-graph/neighborhood/{entity_id}` | `types`, `limit`, `include_inferred` |
| GET | `/api/knowledge-graph/entities/{entity_id}` | knowledge page data |
| GET | `/api/knowledge-graph/path?from=&to=` | shortest explained path |
| GET | `/api/knowledge-graph/search?q=` | entity + speaker lookup |
| GET | `/api/agenda` | days, entries, conflicts, transitions, gaps, change notices, seating notice |
| POST | `/api/agenda/sessions` | `{session_id, note?}` → 201 (409 duplicate, 404 unknown) |
| DELETE | `/api/agenda/sessions/{id}` | remove |
| PUT | `/api/agenda/order` | `{session_ids}` |
| POST | `/api/agenda/acknowledge-changes` | accept current schedule for saved items |
| GET | `/api/agenda/conflicts` | conflicts + tight transitions |
| GET | `/api/agenda/alternatives/{id}` | alternatives for a saved/conflicting session |
| GET | `/api/agenda/export/ics` | `text/calendar` with TZID + VTIMEZONE |
| POST | `/api/assistant/chat` | `{message, history?, context_session_id?}` → answer, mode (`llm`/`retrieval_only`/`no_results`), sessions, speakers, citations, concepts |
| POST | `/api/admin/ingestion` | Bearer admin token; `{remote, force}` → 202, runs in background |
| GET | `/api/admin/ingestion/status` | Bearer admin token; last run status |

Rate-limited (per IP/minute, default 30): intent, recommendations, assistant.
TypeScript contracts: `frontend/types/api.ts`.
