---
description: Implement an approved plan with tests and docs, keeping the app runnable
argument-hint: <approved plan or feature>
---

Implement: **$ARGUMENTS**

1. Load the relevant skills (architecture, plus the domain skill: frontend-design,
   sessionize-ingestion, elasticsearch-search, knowledge-graph, ai-recommendations,
   agenda-management) and follow their workflows.
2. Make the smallest coherent change in the correct layer. Wire services only in
   `backend/app/services/container.py`. Tunables go in `deployment/configuration/`.
3. Keep contracts in sync (`schemas/api.py` ↔ `types/api.ts` ↔ `docs/API.md`).
4. Add tests alongside (see testing-quality skill). Use real data where possible.
5. Verify, and report real output:
   - `cd backend && uv run ruff check app tests && uv run mypy app && uv run pytest tests -q -p no:logging`
   - `cd frontend && npm run typecheck && npm run lint && npm test`
   - UI changes: screenshots via `/audit-ui` and fix visible issues.
6. Update docs touched by the change; add an ADR in `docs/DECISIONS/` for real decisions.
7. Summarize: what changed (files), test results (counts), known limitations.
