---
name: testing-quality
description: Use when writing or running tests, verifying a change, or reporting results for KubeCompass. Covers unit, integration (real data + Elasticsearch), frontend unit, Playwright e2e and visual checks.
---

# Testing & quality

## When to use
Every behavior change, before reporting a task complete, and in `/test`, `/review`, `/release`.

## Scope & layers
| Layer | Location | Needs |
|---|---|---|
| Backend unit | `backend/tests/unit` | nothing (uses real raw JSON where present) |
| Backend integration | `backend/tests/integration` | Elasticsearch on :9200 (isolated `kctest_*` indices, temp data dir) |
| Frontend unit | `frontend/tests/unit` (Vitest + Testing Library) | nothing |
| E2E journey | `frontend/tests/e2e` (Playwright, desktop + mobile) | running API + UI with ingested data |
| Search quality | `uv run kubecompass evaluate` | ES + ingested data |
| Visual | `frontend/scripts/screenshot.mjs` | running stack |

## Workflow
1. Write the test next to the behavior; prefer real KubeCon data over synthetic fixtures; use
   `tests/conftest.py::make_payload` for edge cases the real data lacks.
2. Run the narrowest relevant suite, then the full one:
   `cd backend && uv run ruff check app tests && uv run mypy app && uv run pytest tests -q -p no:logging`
   `cd frontend && npm run typecheck && npm run lint && npm test && npx playwright test`.
3. Report the exact commands and pass/fail counts. Paste failures; never summarize them away.

## Quality requirements
- Tests assert grounding: learn quotes ⊂ abstract, inferred edges have evidence, filters hold
  under semantic search, ICS uses TZID/VTIMEZONE, refresh failures keep the last snapshot.
- No network calls to LLM providers in tests (`KUBECOMPASS_LLM_PROVIDER=none`).

## Expected outputs
Green suites with counts, or failing output plus diagnosis.

## Common mistakes
- Claiming tests pass without running them.
- Integration tests writing to live indices (always use the `kctest` prefix fixture).
- Asserting on data that changes with refreshes (titles of specific sessions) instead of invariants.
