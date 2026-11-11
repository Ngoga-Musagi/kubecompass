# conCompass: architecture and implementation audit

Audit of the KubeCompass codebase (commit `0bb8bf1`, 2026-11-10) against the conCompass brief:
an authorized, context-aware AI event companion. Each section names what exists, what is reusable,
and the gap.

## 1. Existing capabilities

| Area | State | Where |
|---|---|---|
| Sessionize ingestion | Validated, normalized, diffed, versioned; safe refresh with rollback | `backend/app/ingestion/` |
| Multi-event config | One YAML per conference; adapters selected by name; every request is scoped by `conference` | `deployment/configuration/conferences/`, `app/config/conferences.py` |
| Canonical model | Session, Speaker, Entity (topic/technology/project/org), Relationship with provenance | `app/domain/models.py` |
| Search | BM25 + kNN (Jina/bge) + RRF, filters inside both retrievers, synonyms, autocomplete | `app/search/` |
| Knowledge graph | Provenance on every edge (explicit/extracted/curated/inferred); PPR expansion | `app/knowledge_graph/` |
| Recommendations | Intent → editable profile → hybrid + PPR → configurable scoring → tiers + grounded reasons; relevance kept separate from feasibility | `app/recommendation/` |
| Agenda | Add/remove/reorder, conflicts, tight transitions, gaps, alternatives, change notices, ICS with VTIMEZONE | `app/agenda/`, `app/calendar/` |
| Assistant | RAG with [S#]/[P#] citations; uncited LLM answers discarded; works without an LLM | `app/assistant/service.py` |
| LLM layer | Provider chain (OpenAI, Anthropic, Elastic, Ollama) with failover, cool-down and daily budget | `app/infrastructure/llm.py` |
| Identity | Email/username → HMAC attendee id (handle never stored); anonymous = tab-only id | `app/domain/identity.py`, `frontend/lib/guest.ts` |
| Elastic agent | Agent Builder agent with 8 tools + 3 Workflows (Kibana side) | `elasticsearch/agent-builder/`, `elasticsearch/workflows/` |
| UI | Responsive Next.js app (desktop + mobile tested), dark mode, a11y basics | `frontend/` |
| Tests | 75 backend (unit + ES integration), 12 frontend unit, 8 Playwright (desktop + mobile) | `backend/tests`, `frontend/tests` |
| Deploy | One container; Render Blueprint; Kubernetes manifests; Cloud Run guide | `deployment/`, `render.yaml` |

## 2. Reusable as-is
Ingestion pipeline and Sessionize adapter, search service, graph, recommendation and agenda
services, the LLM chain, ICS export, identity, and the whole frontend shell. The new agent is a
layer **on top of** these services: it calls them through typed tools instead of duplicating logic.

## 3. Gaps against the brief

| Brief requirement | Gap | Milestone |
|---|---|---|
| Authorized personal agent (§2A, §2B) | No agent object, no permission model; the assistant is read-only Q&A | **M1 (this change)** |
| Typed tools with authorization + confirmation (§4) | Assistant calls services directly; no tool registry, no confirmation, no audit trail | **M1** |
| Structured responses rendered as cards (§2D, §6) | Assistant returns text + session/speaker lists; no action cards | **M1** |
| Voice (§2C) | None | **M1** (browser speech, modular provider) |
| "What's next / where is my next session / I have 30 minutes" | No time-aware tools | **M1** |
| Branding: conCompass | UI and docs say KubeCompass | **M1** (UI + docs; env prefix and repo name unchanged to keep deployments working) |
| PWA (§2F) | No manifest | **M1** (installable manifest); offline service worker deferred |
| Accounts and roles (§7) | Handle-based identity, no password, no roles | M3 (Google OAuth sign-in comes with Calendar) |
| Google Calendar sync (§2E) | ICS only | M3 |
| Organizer workspace, publishable companion (§3) | None | M4 |
| Tenancy (§2G) | Event isolation exists (per-conference indices and docs); no organization/tenant entity | M4 |
| Luma and other providers (§2H) | Adapter interface exists; only Sessionize implemented | M5–M6 |
| Agent evaluation (§4.9) | Search evaluation exists; no agent evaluation | M8 |

## 4. Data and provider limitations
- Sessionize exposes sessions, speakers, rooms, categories and times. No room capacity, no
  per-session public URL for this event, no venue map; the agent must say so instead of guessing.
- Rooms have names but no coordinates, so "where is my next session" answers with the room and
  venue name only.
- Luma (Phase 2) is event-centric with guest lists; it usually lacks a multi-track program, so the
  canonical model must allow events without sessions. Not verified yet against the live API.

## 5. Agent design (implemented in M1)
- **Permission levels** stored per attendee and per event: `read`, `personalization`, `agenda`,
  `integrations`, `external_actions`. Disabled by default; the attendee enables the agent and picks
  the levels. Checked in the backend tool executor, never only in the UI.
- **Tool registry**: each tool has a typed input model, a required permission and a
  `consequential` flag. Consequential tools (agenda changes) never run from chat; the agent returns
  a *proposal* and the attendee confirms it, which calls a separate endpoint that re-checks
  permissions. Confirmed actions are idempotent (adding a saved session is a no-op) and audited.
- **Planner**: deterministic intent routing for time-aware and agenda tasks (fast, testable, works
  without an LLM); open questions go to the existing grounded RAG answerer. An orchestration
  framework (e.g. LangGraph) is not needed yet; the planner is a plain module so one can be added
  later without touching the tools.
- **Structured response**: `reply` (short text, suitable for speech) plus typed `cards`
  (session, speaker, agenda status, conflict, action proposal) and a `trace` of tools used.

## 6. Voice and mobile readiness
- Voice M1: browser Web Speech API for speech-to-text (push-to-talk only, never background
  listening) and `speechSynthesis` for replies, behind small provider interfaces so a server STT/TTS
  can replace either side independently. Unsupported browsers get text only, with a clear message.
- The layout is already responsive and tested on a 390 px viewport; the agent workspace follows
  the same patterns. A web manifest makes it installable; offline caching is deferred because
  schedules change and stale data is worse than no data.

## 7. Security and authorization risks
| Risk | Status |
|---|---|
| Handle-based identity has no password: anyone who knows a handle sees that agenda | Disclosed in the UI; fixed by OAuth sign-in in M3 |
| Agent could act without consent | M1: consequential tools need explicit permission **and** per-action confirmation |
| Prompt injection via session abstracts | The LLM never executes tools; it only phrases answers from records. Tools are chosen by the deterministic planner |
| Secrets | Server-side only; `.env*` ignored; least-privilege Elastic key documented |
| Rate limiting | Per-IP limiter on expensive endpoints; daily LLM budget |
| Audit | M1 adds an audit trail of confirmed agent actions per attendee |

## 8. UI and usability issues
- The assistant page looks like a generic chat; it needs an agent framing: permissions, suggested
  actions, action cards, voice.
- Long LLM answers do not work when spoken; agent replies are kept to a few sentences, with details
  in cards.

## 9. Prioritized plan
1. **M1: Sessionize attendee experience with an authorized agent (this change).** Permissions,
   typed tools, confirmation and audit, time-aware tools, structured cards, voice, conCompass
   branding, web manifest, tests.
2. M2: Voice and mobile polish (noise handling, PWA offline for the agenda).
3. M3: Google sign-in and Google Calendar sync (OAuth, idempotent event ids, retries, revocation).
4. M4: Organizer workspace and publishable companion (tenants, roles, preview/publish, QR).
5. M5: Luma adapter after verifying the live API.
6. M6–M8: More providers by verified value, graph and discovery improvements, agent evaluation and
   a security review.
