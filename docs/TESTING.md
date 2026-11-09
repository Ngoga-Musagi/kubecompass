# Testing

| Suite | Command | What it proves |
|---|---|---|
| Backend unit (42) | `cd backend && uv run pytest tests/unit` | Sessionize parsing on real data (counts, relationships, provenance, MST offset, missing data), edge cases (duplicates, recurring titles, panel detection, truncated/invalid payloads), extraction evidence & origins, co-occurrence, PPR/paths, overlaps/transitions/gaps, ICS validity (escaping, folding, TZID, VTIMEZONE DST), RRF, filters, demo-persona intent parsing, exclusions, explanation grounding, refresh safety & diffs |
| Backend integration (6) | `uv run pytest tests/integration -p no:logging` | Full journey on real data through HTTP against Elasticsearch in isolated `kctest_*` indices: ingestion → search modes + filters → speakers/graph → intent → recommendations (verbatim quotes) → agenda conflict/409/alternatives → ICS → assistant grounding/no-results → validation & admin auth |
| Static | `uv run ruff check app tests && uv run mypy app` | lint + types |
| Frontend unit (10) | `cd frontend && npm test` | conference-zone time formatting, highlight sanitizing, room labels, RecommendationCard (explanation, quote, breakdown, add-to-agenda), ProfilePanel + editor, empty/error states |
| E2E (3 × desktop/mobile) | `npx playwright test` | Demo journey intent → profile → recommendations → topic page → agenda → alternatives → ICS download; graph interaction; assistant answer + no-results |
| Search quality | `uv run kubecompass evaluate` | P@5 / R@10 / nDCG@10 / latency per method (see SEARCH_DESIGN.md) |
| Visual | `MSYS_NO_PATHCONV=1 node scripts/screenshot.mjs …` | desktop + mobile screenshots, horizontal-overflow and console-error detection |

Last run (2026-11-09): backend 48 passed (42 unit + 6 integration); mypy clean; ruff clean;
frontend 10 passed; tsc + eslint clean; Playwright 3/3 desktop, 3/3 mobile.

Notes: integration and e2e need a running Elasticsearch with ingested data (e2e also needs the API
and UI). Tests never call an LLM provider. Assertions target invariants (grounding, filters,
timezones), not specific session titles, so refreshed data doesn't break them.
