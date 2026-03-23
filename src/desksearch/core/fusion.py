"""Reciprocal Rank Fusion (RRF) for combining multiple ranked result lists.

Performance notes:
- ``weighted_rrf`` uses a fast path with numpy pre-allocated arrays instead of
  Python dict accumulation for the common two-system (BM25 + dense) case.
- ``reciprocal_rank_fusion`` remains dict-based for the generic N-system case.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np


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
    doc_scores: defaultdict[str, float] = defaultdict(float)
    doc_bm25_rank: dict[str, int] = {}
    doc_dense_rank: dict[str, int] = {}

    for system_idx, results in enumerate(result_lists):
        rank_store = doc_bm25_rank if system_idx == 0 else doc_dense_rank
        w = weights[system_idx]
        for rank, (doc_id, _original_score) in enumerate(results, start=1):
            doc_scores[doc_id] += w / (k + rank)
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

    Uses a fast path: builds a doc_id→index mapping, pre-computes RRF
    contributions with numpy vectorized ops, then sorts once.

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

    n_bm25 = len(bm25_results)
    n_dense = len(dense_results)

    if n_bm25 == 0 and n_dense == 0:
        return []

    # Build doc_id → index mapping and rank lookups in one pass.
    doc_ids: list[str] = []
    doc_id_to_idx: dict[str, int] = {}
    doc_bm25_rank: dict[str, int] = {}
    doc_dense_rank: dict[str, int] = {}

    for rank_0, (doc_id, _) in enumerate(bm25_results):
        if doc_id not in doc_id_to_idx:
            doc_id_to_idx[doc_id] = len(doc_ids)
            doc_ids.append(doc_id)
        doc_bm25_rank[doc_id] = rank_0 + 1

    for rank_0, (doc_id, _) in enumerate(dense_results):
        if doc_id not in doc_id_to_idx:
            doc_id_to_idx[doc_id] = len(doc_ids)
            doc_ids.append(doc_id)
        doc_dense_rank[doc_id] = rank_0 + 1

    n_docs = len(doc_ids)

    # Pre-allocate score array and compute RRF contributions with numpy.
    scores = np.zeros(n_docs, dtype=np.float64)

    if n_bm25 > 0 and bm25_weight > 0:
        bm25_indices = np.array(
            [doc_id_to_idx[doc_id] for doc_id, _ in bm25_results], dtype=np.intp
        )
        bm25_ranks = np.arange(1, n_bm25 + 1, dtype=np.float64)
        bm25_contrib = bm25_weight / (k + bm25_ranks)
        np.add.at(scores, bm25_indices, bm25_contrib)

    if n_dense > 0 and dense_weight > 0:
        dense_indices = np.array(
            [doc_id_to_idx[doc_id] for doc_id, _ in dense_results], dtype=np.intp
        )
        dense_ranks = np.arange(1, n_dense + 1, dtype=np.float64)
        dense_contrib = dense_weight / (k + dense_ranks)
        np.add.at(scores, dense_indices, dense_contrib)

    # Sort by descending score using numpy argsort (faster than Python sort).
    sorted_indices = np.argsort(scores)[::-1]

    # Filter out zero-score docs (shouldn't happen, but defensive).
    fused: list[FusedResult] = []
    for idx in sorted_indices:
        s = scores[idx]
        if s <= 0:
            break
        doc_id = doc_ids[idx]
        fused.append(FusedResult(
            doc_id=doc_id,
            score=float(s),
            bm25_rank=doc_bm25_rank.get(doc_id),
            dense_rank=doc_dense_rank.get(doc_id),
        ))

    return fused
