---
name: sessionize-ingestion
description: Use when ingesting, refreshing, validating or normalizing Sessionize conference data, or when the source payload changes shape. Covers validation, normalization, provenance, safe refresh and change detection.
---

# Sessionize ingestion

## When to use
Running/refreshing ingestion, changing normalization, adding a Sessionize-based conference,
or investigating data-quality issues.

## Scope
`app/ingestion/sessionize/{schema,adapter}.py`, `app/ingestion/{pipeline,snapshot,diff}.py`,
conference YAML, `data/raw/`.

## Required inputs
`data/raw/<conf>-all.json` (`/view/All`) and `<conf>-speakers.json` (`/view/Speakers`), or the
endpoints in the conference YAML. Facts verified 2026-11-09: All = sessions/speakers/questions/
categories/rooms; Speakers view uses inline `{id, question, answer}` answers and `{id,name}` sessions.

## Workflow
1. Inspect real data first: `python -I -X utf8 scripts/inspect_sessionize.py data/raw/kubecon-all.json data/raw/kubecon-speakers.json`.
2. If the shape changed, update `schema.py` (extra fields allowed, required fields enforced).
3. Map categories/questions by **title** in the conference YAML (`categories`, `questions`,
   `format_by_track`, `format_by_subtopic`, `format_by_title_without_speakers`).
4. Run `uv run kubecompass ingest` (local) or `--remote` (live). Read the JSON report:
   counts, `rejected_records`, `issues_sample`, `changes`, `error`.
5. On `rejected`: the previous snapshot and ES aliases are untouched. Investigate before `--force`.
6. Confirm freshness: `uv run kubecompass status` and `GET /api/conferences/<id>`.

## Quality requirements
- Times: naive Sessionize times are conference-local; attach the IANA zone, never a fixed offset.
- Duplicates: same id rejected; same title+start+room rejected; same title at different times kept
  (recurring slots).
- Missing data stays missing (`description=None`, `time=None`), recorded in `issues`.
- Provenance on every record: source system/id/url, ingested_at, version, payload hash.
- Refresh refuses payloads with < 10 sessions or a > 30% drop vs the last snapshot (unless `--force`).

## Expected outputs
New snapshot in `data/processed/<conf>/`, swapped ES aliases, change log entries, status JSON.

## Common mistakes
- Treating "Maintainer" in the Company field as an organization (use `non_organization_values`).
- Classifying formats from guesses; only map formats grounded in source category names.
- Deleting the old snapshot before the new one is indexed.
