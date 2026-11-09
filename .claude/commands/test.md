---
description: Run the relevant test suites and report actual results
argument-hint: [unit|integration|frontend|e2e|all] (default: all available)
---

Run tests for: **${ARGUMENTS:-all}**. Follow the testing-quality skill.

1. Check prerequisites: `curl -s localhost:9200` (Elasticsearch) for integration;
   `curl -s localhost:8000/api/health` and `curl -s -o /dev/null -w "%{http_code}" localhost:3000` for e2e.
   If a prerequisite is missing, say which suites are skipped and why. Do not fake them.
2. Run (as applicable):
   - Backend static: `cd backend && uv run ruff check app tests && uv run mypy app`
   - Backend unit: `uv run pytest tests/unit -q`
   - Backend integration: `uv run pytest tests/integration -q -p no:logging`
   - Frontend: `cd frontend && npm run typecheck && npm run lint && npm test`
   - E2E: `npx playwright test --reporter=line`
3. Report a table: suite → command → passed/failed/skipped counts → duration.
4. For failures: paste the assertion and the relevant code location, diagnose the root cause,
   and propose (or, if asked, apply) a fix. Never state tests passed unless they ran and passed.
