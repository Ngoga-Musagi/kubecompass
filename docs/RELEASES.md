# Releases

## 0.1.0 (2026-11-09)
First complete vertical slice on real KubeCon NA 2026 data (600 sessions, 712 speakers).
- Sessionize adapter, safe refresh, change detection, provenance.
- Elasticsearch BM25 / kNN / hybrid (app + native RRF), filters, facets, autocomplete.
- Knowledge graph (1,814 nodes, 9,249 edges) with evidence; interactive explorer.
- Explainable recommendations (Must Attend / Highly Relevant / Explore), editable profile.
- Agenda with conflicts, transitions, gaps, alternatives, change notices, ICS export.
- Grounded assistant (LLM optional).
- Evaluation: hybrid nDCG@10 0.771 vs BM25 0.735 / vector 0.708 (12 queries, assistant-judged).
Known limitations: see README.
