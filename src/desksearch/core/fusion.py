"""Reciprocal Rank Fusion (RRF) for combining multiple ranked result lists."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FusedResult:
    """A single fused search result with its combined score."""
    doc_id: str
    score: float
    bm25_rank: int | None = None
    dense_rank: int | None = None


def reciprocal_rank_fusion(
    *result_lists: list[tuple[str, float]],
    k: int = 60,
    weights: list[float] | None = None,
) -> list[FusedResult]:
    """Combine multiple ranked result lists using Reciprocal Rank Fusion.

    RRF score for document d = sum over systems s of: weight_s / (k + rank_s(d))

    Args:
        *result_lists: Each list is [(doc_id, score)] sorted by descending score.
        k: RRF constant (default 60, as in the original paper).
            Higher k reduces the impact of high rankings.
        weights: Optional per-system weights. Defaults to equal weight (1.0).

    Returns:
        Fused results sorted by descending RRF score.
    """
    n_systems = len(result_lists)
    if n_systems == 0:
        return []

    if weights is None:
        weights = [1.0] * n_systems
    elif len(weights) != n_systems:
        raise ValueError(f"Expected {n_systems} weights, got {len(weights)}")

    # Track per-system ranks for diagnostics
    doc_scores: dict[str, float] = {}
    doc_bm25_rank: dict[str, int] = {}
    doc_dense_rank: dict[str, int] = {}

    for system_idx, results in enumerate(result_lists):
        rank_store = doc_bm25_rank if system_idx == 0 else doc_dense_rank
        for rank, (doc_id, _original_score) in enumerate(results, start=1):
            rrf_contribution = weights[system_idx] / (k + rank)
            doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + rrf_contribution
            rank_store[doc_id] = rank

    fused = [
        FusedResult(
            doc_id=doc_id,
            score=score,
            bm25_rank=doc_bm25_rank.get(doc_id),
            dense_rank=doc_dense_rank.get(doc_id),
        )
        for doc_id, score in doc_scores.items()
    ]
    fused.sort(key=lambda r: r.score, reverse=True)
    return fused


def weighted_rrf(
    bm25_results: list[tuple[str, float]],
    dense_results: list[tuple[str, float]],
    alpha: float = 0.5,
    k: int = 60,
) -> list[FusedResult]:
    """Convenience wrapper for two-system fusion with an alpha weight.

    Args:
        bm25_results: BM25 scored results.
        dense_results: Dense/vector scored results.
        alpha: Weight balance. 0.0 = BM25 only, 1.0 = dense only.
            Default 0.5 gives equal weight.
        k: RRF constant.

    Returns:
        Fused results sorted by descending score.
    """
    bm25_weight = 1.0 - alpha
    dense_weight = alpha
    return reciprocal_rank_fusion(
        bm25_results,
        dense_results,
        k=k,
        weights=[bm25_weight, dense_weight],
    )
