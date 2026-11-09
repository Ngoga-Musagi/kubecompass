"""Reciprocal Rank Fusion.

We fuse in the application by default (rather than only via the native ES `rrf`
retriever) because explanations need each retriever's individual rank. The
native retriever is still supported and compared in the evaluation.
"""

from __future__ import annotations

from collections.abc import Sequence


def rrf(
    rankings: Sequence[Sequence[str]], k: int = 60, weights: Sequence[float] | None = None
) -> dict[str, float]:
    """Return {doc_id: fused score}. `rankings` are best-first id lists."""
    weights = weights or [1.0] * len(rankings)
    scores: dict[str, float] = {}
    for ranking, w in zip(rankings, weights, strict=True):
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + w / (k + rank)
    return scores
