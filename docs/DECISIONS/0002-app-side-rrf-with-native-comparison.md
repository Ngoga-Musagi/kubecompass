# 0002 App-side RRF by default, native ES RRF supported

Status: accepted

**Context.** Hybrid retrieval needs fusion; explanations need each retriever's rank.

**Decision.** Fuse BM25 and kNN results with Reciprocal Rank Fusion (k = 60) in the application,
running both retrievers with identical filters. `mode=hybrid_native` uses the ES `rrf` retriever.

**Evidence.** On the 12-query evaluation both produce identical rankings (nDCG@10 0.771); native
is ~2× faster (44 vs 90 ms) because it is one round trip.

**Consequences.** Slightly higher latency for explainability. Switch `KUBECOMPASS_FUSION_MODE`
or call `hybrid_native` when per-retriever ranks aren't needed.
