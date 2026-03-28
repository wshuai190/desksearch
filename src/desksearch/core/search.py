"""Hybrid search engine combining BM25 and dense retrieval.

Graceful degradation:
- If FAISS is unavailable (import error or corrupt index), the engine
  automatically falls back to BM25-only search.
- If tantivy is unavailable, the engine falls back to dense-only search.
- Both components failing is treated as a hard error at init time.

Performance monitoring:
- Searches slower than ``SLOW_SEARCH_MS`` emit a WARNING log entry so
  operators can identify queries that need optimisation.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import partial
from typing import Optional

import numpy as np

# Module-level thread pool for parallel BM25 + dense search.
# 2 workers are enough (one per backend); daemon threads exit when the
# process exits without needing explicit shutdown.
_SEARCH_EXECUTOR: concurrent.futures.ThreadPoolExecutor = (
    concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="ds-search")
)

from desksearch.config import Config
from desksearch.core.bm25 import BM25Index
from desksearch.core.dense import DenseIndex
from desksearch.core.fusion import FusedResult, weighted_rrf
from desksearch.core.snippets import Snippet, QueryMatcher, extract_snippets_with_pattern, make_query_pattern

logger = logging.getLogger(__name__)

# Log a warning for searches that take longer than this threshold.
SLOW_SEARCH_MS = 100

# ---------------------------------------------------------------------------
# Query expansion
# ---------------------------------------------------------------------------

# Static synonym table for common technical abbreviations.
# Keys are lower-case; values are additional space-separated terms appended to
# the BM25 query (tantivy default is OR semantics between terms).
_TECH_SYNONYMS: dict[str, list[str]] = {
    "ml":   ["machine learning"],
    "ai":   ["artificial intelligence"],
    "nlp":  ["natural language processing"],
    "ir":   ["information retrieval"],
    "dl":   ["deep learning"],
    "nn":   ["neural network"],
    "llm":  ["large language model"],
    "rag":  ["retrieval augmented generation"],
    "api":  ["application programming interface"],
    "db":   ["database"],
    "py":   ["python"],
    "js":   ["javascript"],
    "ts":   ["typescript"],
    "img":  ["image", "picture", "photo"],
    "doc":  ["document", "documentation"],
    "repo": ["repository"],
    "cv":   ["computer vision"],
}

_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "and", "or", "not", "no", "but", "if", "then", "so", "as",
    "it", "its", "this", "that", "these", "those",
})


def _is_short_keyword_query(query: str) -> bool:
    """Return True if the query looks like a short keyword/exact-match query.

    Characteristics: ≤3 content words, no question words, no natural-language
    phrasing.  These queries benefit from higher BM25 weight.
    """
    tokens = re.findall(r"\w+", query.lower())
    content_tokens = [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]
    question_words = {"what", "why", "how", "when", "where", "who", "which"}
    has_question = any(t in question_words for t in tokens)
    return (
        len(content_tokens) <= 3
        and not has_question
        and len(tokens) <= 5
    )


def _expand_query_for_bm25(query: str) -> str:
    """Expand a short query with synonym/variant terms for better BM25 recall.

    Only applied to queries with ≤4 content words.  Expansion is additive
    (extra terms appended) so tantivy's default OR semantics between terms
    pick them up without needing complex boolean syntax.

    Returns the original query unchanged if no expansion is warranted or if
    the query is long enough to not benefit.
    """
    tokens = re.findall(r"\w+", query)
    content = [t for t in tokens if t.lower() not in _STOP_WORDS and len(t) > 1]

    if len(content) > 4:
        return query

    extra: list[str] = []
    for token in content:
        lower = token.lower()

        # Tech acronym expansion
        if lower in _TECH_SYNONYMS:
            extra.extend(_TECH_SYNONYMS[lower])

        # Simple morphological variants
        if lower.endswith("ing") and len(lower) > 5:
            base = lower[:-3]
            extra.append(base)
            extra.append(base + "e")
        elif lower.endswith("tion") and len(lower) > 6:
            extra.append(lower[:-4])
            extra.append(lower[:-4] + "te")
        elif lower.endswith("s") and len(lower) > 3 and not lower.endswith("ss"):
            extra.append(lower[:-1])
        elif len(lower) > 3:
            extra.append(lower + "s")

    if not extra:
        return query

    # Deduplicate while preserving order; exclude terms already in query
    seen: set[str] = {t.lower() for t in tokens}
    query_lower = query.lower()
    unique_extra: list[str] = []
    for term in extra:
        t_lower = term.lower()
        if t_lower not in seen and t_lower not in query_lower:
            seen.add(t_lower)
            unique_extra.append(term)

    if not unique_extra:
        return query

    return query + " " + " ".join(unique_extra)

# ---------------------------------------------------------------------------
# LRU doc-text cache
# ---------------------------------------------------------------------------

# Maximum chunk texts to keep in RAM. Each chunk ≈ 512 chars ≈ 0.5 KB,
# so 512 entries ≈ 256 KB — negligible compared to an unbounded dict that
# previously held ALL indexed texts (tens of MB for large corpora).
_DOC_TEXT_CACHE_SIZE = 512


class _LRUTextCache:
    """Bounded LRU cache: doc_id → chunk text.

    Falls back to BM25 for cache misses so snippet extraction always works
    without requiring all texts to live in RAM.
    """

    __slots__ = ("_cache", "_maxsize")

    def __init__(self, maxsize: int = _DOC_TEXT_CACHE_SIZE) -> None:
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        if key not in self._cache:
            return default
        self._cache.move_to_end(key)
        return self._cache[key]

    def __setitem__(self, key: str, value: str) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def pop(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self._cache.pop(key, default)

    def __len__(self) -> int:
        return len(self._cache)


# ---------------------------------------------------------------------------
# Search result cache
# ---------------------------------------------------------------------------


class _SearchCache:
    """Thread-safe LRU cache for search results.

    Keyed on (query, top_k, alpha). Fully invalidated on any index mutation
    (add or delete). This avoids stale results while keeping the implementation
    simple — mutations are infrequent compared to searches.
    """

    def __init__(self, maxsize: int = 256) -> None:
        self._cache: OrderedDict[tuple, list] = OrderedDict()
        self._maxsize = maxsize
        self._lock = threading.Lock()

    def get(self, query: str, top_k: int, alpha: float) -> list | None:
        key = (query, top_k, round(alpha, 4))
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    def put(self, query: str, top_k: int, alpha: float, results: list) -> None:
        key = (query, top_k, round(alpha, 4))
        with self._lock:
            self._cache[key] = results
            self._cache.move_to_end(key)
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        """Invalidate the entire cache (call on any index mutation)."""
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._cache)


@dataclass(frozen=True)
class SearchResult:
    """A single search result with score, ranking info, and snippets."""
    doc_id: str
    score: float
    snippets: list[Snippet] = field(default_factory=list)
    bm25_rank: int | None = None
    dense_rank: int | None = None


class HybridSearchEngine:
    """Ties together BM25, dense retrieval, fusion, and snippet extraction.

    Automatically degrades to single-backend mode when one component fails:
    - ``bm25.available=False``  → dense-only search
    - ``dense.available=False`` → BM25-only search

    Usage::

        engine = HybridSearchEngine(config)
        engine.add_document("chunk123", "full text here", embedding_vector)
        results = await engine.search("my query", query_embedding)
    """

    def __init__(
        self,
        config: Config,
        *,
        alpha: float = 0.4,
        rrf_k: int = 60,
        dimension: int = 64,
        cache_size: int = 256,
    ) -> None:
        """Initialize the hybrid search engine.

        Args:
            config: Application configuration (provides data_dir).
            alpha: Fusion weight. 0.0 = BM25 only, 1.0 = dense only.
                Default 0.4 gives BM25 a slight edge (keyword queries win).
            rrf_k: RRF constant.
            dimension: Embedding vector dimension.
            cache_size: Maximum number of query results to cache (LRU).
                Set to 0 to disable caching.
        """
        self._config = config
        self._alpha = alpha
        self._rrf_k = rrf_k

        self.bm25 = BM25Index(config.data_dir)
        self.dense = DenseIndex(config.data_dir, dimension=dimension)

        # Log degradation warnings at startup.
        if not self.bm25.available:
            logger.warning(
                "BM25 index unavailable — search will use dense-only mode. "
                "Keyword matching and snippet extraction may be degraded."
            )
        if not self.dense.available:
            logger.warning(
                "Dense (FAISS) index unavailable — search will use BM25-only mode. "
                "Semantic/vector search is disabled."
            )
        if not self.bm25.available and not self.dense.available:
            logger.error(
                "Both BM25 and FAISS indexes are unavailable. "
                "Search will return no results."
            )

        # Bounded LRU cache of recently-accessed doc texts for snippets.
        self._doc_texts: _LRUTextCache = _LRUTextCache(_DOC_TEXT_CACHE_SIZE)

        # LRU result cache — avoids re-running search for repeated queries.
        self._cache: _SearchCache | None = (
            _SearchCache(maxsize=cache_size) if cache_size > 0 else None
        )

    # ------------------------------------------------------------------
    # Component health
    # ------------------------------------------------------------------

    def _compute_alpha(self, query: str, alpha_override: Optional[float]) -> float:
        """Return effective fusion alpha for this query.

        Short keyword queries get a slightly lower alpha (more BM25 weight)
        because exact matching is usually more useful there.  Long natural-
        language queries get the default alpha (balanced hybrid).
        """
        if alpha_override is not None:
            return alpha_override
        if _is_short_keyword_query(query):
            return max(0.0, self._alpha - 0.1)
        return self._alpha

    @property
    def mode(self) -> str:
        """Return the active search mode: 'hybrid', 'bm25_only', 'dense_only', or 'unavailable'."""
        bm25_ok = self.bm25.available
        dense_ok = self.dense.available
        if bm25_ok and dense_ok:
            return "hybrid"
        if bm25_ok:
            return "bm25_only"
        if dense_ok:
            return "dense_only"
        return "unavailable"

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def add_document(
        self, doc_id: str, text: str, embedding: np.ndarray
    ) -> None:
        """Index a document in both BM25 and dense indexes."""
        self.bm25.add_document(doc_id, text)
        self.dense.add(doc_id, embedding)
        self._doc_texts[doc_id] = text
        if self._cache:
            self._cache.clear()

    def add_documents(
        self,
        docs: list[tuple[str, str, np.ndarray]],
        *,
        defer_save: bool = False,
    ) -> None:
        """Batch-index documents as (doc_id, text, embedding) triples.

        Args:
            docs: List of (doc_id, text, embedding) triples.
            defer_save: If True, skip persisting the FAISS index to disk.
                Caller must call ``save()`` when done.  Use during bulk
                indexing to avoid O(N²) I/O from saving after every batch.
        """
        if not docs:
            return
        bm25_batch = [(doc_id, text) for doc_id, text, _ in docs]
        dense_batch = [(doc_id, emb) for doc_id, _, emb in docs]

        self.bm25.add_documents(bm25_batch)
        self.dense.add_batch(dense_batch, defer_save=defer_save)

        for doc_id, text, _ in docs:
            self._doc_texts[doc_id] = text

        if self._cache:
            self._cache.clear()

    def delete_document(self, doc_id: str) -> None:
        """Remove a document from all indexes."""
        self.bm25.delete_document(doc_id)
        self.dense.delete(doc_id)
        self._doc_texts.pop(doc_id, None)
        if self._cache:
            self._cache.clear()

    def save(self) -> None:
        """Persist all indexes to disk."""
        if self.dense and self.dense.available:
            self.dense.save()
        # BM25 (tantivy) auto-commits on write

    def clear(self) -> None:
        """Clear all indexes and caches.

        Reinitialises BM25 and FAISS from scratch so callers can rebuild
        the search engine after bulk deletions.
        """
        # Recreate the BM25 index (tantivy) — clear by rebuilding
        try:
            if self.bm25.available:
                self.bm25 = BM25Index(self._config.data_dir)
        except Exception as exc:
            logger.warning("Failed to clear BM25 index: %s", exc)

        # Recreate the FAISS index
        try:
            if self.dense.available:
                self.dense = DenseIndex(
                    self._config.data_dir,
                    dimension=self.dense._dimension,
                )
        except Exception as exc:
            logger.warning("Failed to clear dense index: %s", exc)

        # Clear text and result caches
        self._doc_texts = _LRUTextCache(_DOC_TEXT_CACHE_SIZE)
        if self._cache:
            self._cache.clear()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        query_embedding: np.ndarray,
        top_k: int = 10,
        *,
        alpha: Optional[float] = None,
        max_snippets: int = 3,
        boosts: Optional[dict[str, float]] = None,
    ) -> list[SearchResult]:
        """Run hybrid search: BM25 + dense retrieval with RRF fusion.

        Automatically degrades to single-backend mode when one component is
        unavailable.  Searches slower than SLOW_SEARCH_MS are logged as
        warnings.

        Args:
            query: Raw search query string.
            query_embedding: Dense embedding of the query.
            top_k: Number of results to return.
            alpha: Override the default fusion weight for this query.
            max_snippets: Max snippets per result.
            boosts: Optional {doc_id: multiplier} map for post-fusion score
                boosting (e.g. filename match, recency).  When provided the
                result is NOT stored in the cache.

        Returns:
            Ranked list of SearchResult objects.
        """
        t_start = time.perf_counter()
        fusion_alpha = self._compute_alpha(query, alpha)
        query_norm = query.strip()

        # Fast path: return cached results (only when no custom boosts).
        if self._cache and boosts is None:
            cached = self._cache.get(query_norm, top_k, fusion_alpha)
            if cached is not None:
                logger.debug("Cache hit for query %r", query_norm)
                return cached

        # FIX: use get_running_loop() instead of deprecated get_event_loop()
        loop = asyncio.get_running_loop()

        results = await loop.run_in_executor(
            None,
            partial(
                self._search_sync_inner,
                query_norm, query_embedding, top_k, fusion_alpha, max_snippets, boosts,
            ),
        )

        elapsed_ms = (time.perf_counter() - t_start) * 1000
        if elapsed_ms > SLOW_SEARCH_MS:
            logger.warning(
                "Slow search (%.0fms) for query %r — mode=%s top_k=%d",
                elapsed_ms, query_norm, self.mode, top_k,
            )
        else:
            logger.debug("Search %r: %.1fms (%d results)", query_norm, elapsed_ms, len(results))

        if self._cache and boosts is None:
            self._cache.put(query_norm, top_k, fusion_alpha, results)

        return results

    def search_sync(
        self,
        query: str,
        query_embedding: np.ndarray,
        top_k: int = 10,
        *,
        alpha: Optional[float] = None,
        max_snippets: int = 3,
        boosts: Optional[dict[str, float]] = None,
    ) -> list[SearchResult]:
        """Synchronous version of search for non-async contexts."""
        t_start = time.perf_counter()
        fusion_alpha = self._compute_alpha(query, alpha)
        query_norm = query.strip()

        # Fast path: return cached results (only when no custom boosts).
        if self._cache and boosts is None:
            cached = self._cache.get(query_norm, top_k, fusion_alpha)
            if cached is not None:
                return cached

        results = self._search_sync_inner(
            query_norm, query_embedding, top_k, fusion_alpha, max_snippets, boosts,
        )

        elapsed_ms = (time.perf_counter() - t_start) * 1000
        if elapsed_ms > SLOW_SEARCH_MS:
            logger.warning(
                "Slow search (%.0fms) for query %r — mode=%s top_k=%d",
                elapsed_ms, query_norm, self.mode, top_k,
            )

        if self._cache and boosts is None:
            self._cache.put(query_norm, top_k, fusion_alpha, results)

        return results

    def _search_sync_inner(
        self,
        query_norm: str,
        query_embedding: np.ndarray,
        top_k: int,
        fusion_alpha: float,
        max_snippets: int,
        boosts: Optional[dict[str, float]] = None,
    ) -> list[SearchResult]:
        """Core search logic, called from both async and sync wrappers."""
        mode = self.mode
        if mode == "unavailable":
            return []

        # Determine effective alpha based on available backends.
        if mode == "bm25_only":
            effective_alpha = 0.0
        elif mode == "dense_only":
            effective_alpha = 1.0
        else:
            effective_alpha = fusion_alpha

        # Expand the query for BM25 (synonym/variant expansion for short queries).
        bm25_query = _expand_query_for_bm25(query_norm) if mode in ("hybrid", "bm25_only") else query_norm

        # Run available backends — in parallel when both are needed.
        bm25_results: list[tuple[str, float]] = []
        dense_results: list[tuple[str, float]] = []

        need_bm25  = mode in ("hybrid", "bm25_only")
        need_dense = mode in ("hybrid", "dense_only")

        if need_bm25 and need_dense:
            # Submit both to the executor and collect results concurrently.
            ft_bm25  = _SEARCH_EXECUTOR.submit(self.bm25.search,  bm25_query,      top_k * 2)
            ft_dense = _SEARCH_EXECUTOR.submit(self.dense.search, query_embedding, top_k * 2)
            try:
                bm25_results = ft_bm25.result()
            except Exception as exc:
                logger.error("BM25 search error: %s", exc, exc_info=True)
            try:
                dense_results = ft_dense.result()
            except Exception as exc:
                logger.error("Dense search error: %s", exc, exc_info=True)
        else:
            if need_bm25:
                try:
                    bm25_results = self.bm25.search(bm25_query, top_k=top_k * 2)
                except Exception as exc:
                    logger.error("BM25 search error: %s", exc, exc_info=True)
            if need_dense:
                try:
                    dense_results = self.dense.search(query_embedding, top_k=top_k * 2)
                except Exception as exc:
                    logger.error("Dense search error: %s", exc, exc_info=True)

        # Fuse results.
        fused = weighted_rrf(
            bm25_results, dense_results, alpha=effective_alpha, k=self._rrf_k
        )

        # Apply optional per-document score boosts (multiplicative).
        if boosts:
            fused = _apply_boosts(fused, boosts)

        return self._build_results(query_norm, fused[:top_k], max_snippets)

    def _build_results(
        self,
        query: str,
        fused: list[FusedResult],
        max_snippets: int,
    ) -> list[SearchResult]:
        """Convert fused results into SearchResult objects with snippets."""
        matcher: QueryMatcher | None = make_query_pattern(query)

        results: list[SearchResult] = []
        for fr in fused:
            text = self._doc_texts.get(fr.doc_id) or self.bm25.get_document(fr.doc_id)
            snippets: list[Snippet] = []
            if text:
                snippets = extract_snippets_with_pattern(
                    text, matcher, max_snippets=max_snippets
                )

            results.append(SearchResult(
                doc_id=fr.doc_id,
                score=fr.score,
                snippets=snippets,
                bm25_rank=fr.bm25_rank,
                dense_rank=fr.dense_rank,
            ))
        return results

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    @property
    def doc_count(self) -> int:
        """Number of documents in the BM25 index (or FAISS if BM25 unavailable)."""
        if self.bm25.available:
            return self.bm25.doc_count
        return self.dense.doc_count

    @property
    def cache_size(self) -> int:
        """Number of entries currently held in the result cache."""
        return self._cache.size if self._cache else 0

    def set_doc_text(self, doc_id: str, text: str) -> None:
        """Register document text for snippet extraction without re-indexing."""
        self._doc_texts[doc_id] = text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_boosts(
    fused: list[FusedResult],
    boosts: dict[str, float],
) -> list[FusedResult]:
    """Apply multiplicative score boosts and re-sort fused results.

    Args:
        fused: Sorted list of FusedResult objects (descending score).
        boosts: Mapping of doc_id → multiplier.  Missing entries get ×1.0.

    Returns:
        New list sorted by boosted scores descending.
    """
    if not boosts:
        return fused

    boosted: list[FusedResult] = []
    for fr in fused:
        multiplier = boosts.get(fr.doc_id, 1.0)
        if multiplier != 1.0:
            fr = FusedResult(
                doc_id=fr.doc_id,
                score=fr.score * multiplier,
                bm25_rank=fr.bm25_rank,
                dense_rank=fr.dense_rank,
            )
        boosted.append(fr)

    boosted.sort(key=lambda r: r.score, reverse=True)
    return boosted
