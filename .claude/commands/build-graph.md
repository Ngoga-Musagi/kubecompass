---
description: Rebuild the knowledge graph and audit entity/relationship quality
argument-hint: [entity id to spot-check, e.g. topic:gpu-scheduling]
---

Rebuild and audit the knowledge graph. Follow the knowledge-graph skill.

1. Re-run extraction and indexing: `cd backend && uv run kubecompass ingest`.
2. Report `graph` stats: entities by type, relationships by origin, related-session edges.
3. Audit quality with a short script against `data/processed/kubecon-na-2026/dataset.json`:
   - Top 25 topics/technologies/projects by `session_count`.
   - Entities linked to < 2 sessions (candidates for noise) and very broad ones (> 40% of sessions).
   - 10 random extracted edges: print entity, session title and `evidence`; judge whether the
     evidence supports the link.
   - Count relationships with `origin != explicit` and missing evidence (must be 0).
4. Spot-check ${ARGUMENTS:-topic:gpu-scheduling}: `GET /api/knowledge-graph/neighborhood/<id>` and
   `/graph?focus=<id>` in the UI.
5. Propose vocabulary fixes (aliases to tighten/add, `strict_match`, `low_signal`) and, if asked,
   apply them and repeat steps 1–4 showing before/after counts.
