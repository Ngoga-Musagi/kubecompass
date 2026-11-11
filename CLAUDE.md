# conCompass: project guide for Claude

conCompass (formerly KubeCompass; the repo, env prefix `KUBECOMPASS_*` and storage keys keep the old
name so deployments keep working) is an AI event companion: every attendee gets a personal,
**authorized** agent for an event that finds the right sessions and people, **explains why with
evidence**, plans a conflict-free agenda and says where to be next, by text or voice. First event:
KubeCon + CloudNativeCon NA 2026 via Sessionize. Roadmap: `docs/CONCOMPASS_AUDIT.md`.

## Product principles (non-negotiable)
1. **Real data only.** Never invent sessions, speakers, rooms, times, formats, scores or stats.
   Missing source fields are shown as unavailable.
2. **Provenance everywhere.** Every entity/edge carries `origin` (`explicit` from Sessionize,
   `extracted` from text with a quoted sentence, `curated` vocabulary, `inferred` by the app).
   Inferred ≠ fact in the UI or the assistant.
3. **Visual quality is a feature.** Discovery dashboard first. Follow `docs/UI_DESIGN.md` and the
   `frontend-design` skill. No placeholder buttons.
4. **Relevance ≠ feasibility.** Agenda conflicts never lower a recommendation's score.
5. **Works without an LLM.** Rules/extractive fallbacks are first-class; an LLM only enhances.
   Providers (Anthropic, OpenAI, Ollama/local) are chained in `app/infrastructure/llm.py`.
6. **Elasticsearch is the core** search and indexed-data layer (BM25 + kNN + RRF + filters).
7. **The agent acts only with permission and confirmation.** Permissions are per attendee per
   event and enforced in `app/agent/tools.py`, never only in the UI. Consequential tools (agenda
   changes, later external actions) are proposed, then run via `/api/agent/actions` after the
   attendee confirms; they are idempotent and audited. The LLM never selects or runs tools.
8. **Voice is push-to-talk.** No background listening; speech providers stay behind
   `frontend/lib/voice.ts` interfaces. Agent replies are short and speakable; details go in cards.

## Architecture (see docs/ARCHITECTURE.md)
```
Sessionize JSON → ingestion adapter → canonical model → vocabulary extraction + graph build
  → embeddings (FastEmbed, local) → Elasticsearch (versioned indices behind aliases)
  → FastAPI services (search · graph [NetworkX read model] · recommendations · agenda · assistant)
  → event agent (intent routing → permission-checked typed tools → structured cards)
  → Next.js UI (+ voice, installable manifest)
```
- `backend/app/` – `ingestion/` (adapters, pipeline, snapshot/diff), `knowledge_graph/`,
  `search/`, `recommendation/`, `agenda/`, `calendar/`, `assistant/`, `agent/` (permissions,
  tools, planner; see docs/AGENT.md), `api/`, `infrastructure/`.
- `frontend/` – Next.js 15 App Router, Tailwind v4 tokens in `app/globals.css`, components by domain.
- `deployment/configuration/` – per-conference YAML, vocabulary, ranking weights (no code changes
  needed to tune or to add a conference).
- `elasticsearch/` – mappings + shared analysis (synonyms).

## Commands
| Task | Command |
|---|---|
| Start ES | `docker compose up -d elasticsearch` |
| Ingest / refresh | `cd backend && uv run kubecompass ingest [--remote] [--force]` |
| API | `cd backend && uv run uvicorn app.main:app --port 8000` |
| UI | `cd frontend && npm run dev` |
| Backend tests | `cd backend && uv run pytest tests/unit` · integration: `tests/integration` (needs ES) |
| Frontend tests | `cd frontend && npm test` · e2e: `npx playwright test` (needs running stack) |
| Lint/types | `uv run ruff check app tests && uv run mypy app` · `npm run lint && npm run typecheck` |
| Evaluate search | `cd backend && uv run kubecompass evaluate` |
| Screenshots | `cd frontend && MSYS_NO_PATHCONV=1 node scripts/screenshot.mjs / /agenda` |
Windows/Git Bash: set `MSYS_NO_PATHCONV=1` when passing URL paths; `uvicorn --reload` can leave
an orphaned worker on :8000 (find with `netstat -ano | grep :8000`).

## Environments
Local (default `.env`, Docker ES, FastEmbed) and Elastic Cloud (`KUBECOMPASS_ENV_FILE=.env.cloud`,
Serverless, Jina via `_inference`, Agent Builder + Workflows from `elasticsearch/agent-builder` and
`elasticsearch/workflows`, provisioned by `kubecompass elastic setup`). See docs/ELASTIC_CLOUD.md.

## Conventions
- Python 3.12, typed, Pydantic models for every boundary; ruff (line 100) + mypy clean.
- Small focused modules; services are wired only in `app/services/container.py`.
- API errors: `{"error": {"code", "message"}}`; never leak internals. Guest identity = `X-Guest-Id` UUID.
- TypeScript strict; API types in `frontend/types/api.ts` mirror `backend/app/schemas/api.py`.
- All times rendered in the conference IANA zone (`America/Denver`), never the viewer's.
- Tunables live in YAML (`ranking.yaml`, vocabulary, conference config), not in code.

## How to work here
1. Inspect before creating; read the relevant skill in `.claude/skills/` first.
2. Plan substantial changes with `/plan`; implement with `/implement`; verify with `/test`.
3. Keep the app runnable; add tests with every behavior change; run them and report real results.
4. UI changes: run `/audit-ui` (screenshots at desktop + mobile) and fix what you see.
5. Record significant decisions in `docs/DECISIONS/` (ADR format).
6. Never commit `.env`, API keys, or `data/processed/`.

## Skills & commands
Skills: `architecture`, `frontend-design`, `sessionize-ingestion`, `elasticsearch-search`,
`knowledge-graph`, `ai-recommendations`, `agenda-management`, `testing-quality`, `event-agent`,
`voice-interaction`.
Commands: `/plan` `/implement` `/review` `/test` `/ingest-data` `/build-graph`
`/evaluate-search` `/audit-ui` `/release`.
