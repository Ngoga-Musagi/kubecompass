---
description: Run the search/recommendation evaluation and compare retrieval approaches
argument-hint: [path to queries.json]
---

Evaluate retrieval quality. Follow the elasticsearch-search skill.

1. Prerequisites: ES up and data ingested (`uv run kubecompass status`).
2. Run `cd backend && uv run kubecompass evaluate ${ARGUMENTS:+--dataset $ARGUMENTS}`.
3. Present a table from `data/evaluation/results.json`: method → P@5, R@10, nDCG@10, latency,
   explanation coverage, for BM25, vector, hybrid (app RRF), hybrid (native RRF), hybrid + graph,
   personalized pipeline.
4. Interpret honestly: note the judgment method (pooled, assistant-judged, 12 queries), that small
   differences are within noise, and that pooling favors the evaluated methods.
   Do not claim graph expansion or personalization "improves relevance" unless the numbers show it.
5. If adding queries: build a pool with `app.services.evaluation.build_pool`, judge 0/1/2 from title
   and abstract, record the judgment method in the file, then re-run.
6. Update the results section of `docs/SEARCH_DESIGN.md` when numbers change.
