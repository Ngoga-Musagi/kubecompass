---
description: Run release quality gates, verify configuration and deployment, update release docs
argument-hint: [version, e.g. 0.2.0]
---

Prepare release **${ARGUMENTS:-next}**.

1. Quality gates (all must pass; report real counts):
   - `/test all` (backend static + unit + integration, frontend typecheck/lint/unit, Playwright e2e).
   - `cd backend && uv run kubecompass evaluate`: no unexplained regression vs `docs/SEARCH_DESIGN.md`.
   - `/audit-ui` on the main pages (desktop + mobile).
2. Configuration: `.env.example` lists every setting in `backend/app/config/settings.py`;
   no secrets tracked (`git ls-files | grep -E "\.env$"` must be empty); admin token required in prod.
3. Deployment: `docker compose build` succeeds; `docker compose up -d` → backend healthy
   (`/api/health` = ok), frontend serves `/`; data ingested via `kubecompass ensure`.
4. Docs: update `README.md` (setup/run), `docs/API.md` for contract changes, and add a dated
   section to `docs/RELEASES.md` with features, fixes, evaluation numbers and known limitations.
5. Bump versions (`backend/pyproject.toml`, `frontend/package.json`) and summarize; do not tag or
   push unless asked.
