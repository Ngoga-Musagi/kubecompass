---
description: Inspect, validate, normalize and index Sessionize data; report counts, rejects and freshness
argument-hint: [--remote] [--force] [--conference <id>]
---

Ingest conference data (args: **${ARGUMENTS:-local files, default conference}**). Follow the
sessionize-ingestion skill.

1. Ensure Elasticsearch is up: `docker compose up -d elasticsearch` then `curl -s localhost:9200`.
2. Inspect the raw files first:
   `python -I -X utf8 scripts/inspect_sessionize.py data/raw/kubecon-all.json data/raw/kubecon-speakers.json`
   Flag any structural change versus `backend/app/ingestion/sessionize/schema.py`.
3. Run `cd backend && uv run kubecompass $ARGUMENTS ingest` (use `--remote` to fetch live endpoints).
4. Report from the JSON output: state, version, origin, session/speaker/room/track counts,
   embedded counts, rejected records (with reasons), issues, changes (added/removed/modified),
   graph stats, and `error` if any.
5. If `state` is `rejected`/`failed`, confirm the previous snapshot is still served
   (`uv run kubecompass status`, `GET /api/conferences/<id>` → `data_version`) and explain the cause.
   Do not use `--force` without the user's agreement.
