"""Hybrid search engine combining BM25 and dense retrieval."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import partial
from typing import Optional

import numpy as np

from desksearch.config import Config
from desksearch.core.bm25 import BM25Index
from desksearch.core.dense import DenseIndex
from desksearch.core.fusion import FusedResult, weighted_rrf
from desksearch.core.snippets import Snippet, QueryMatcher, extract_snippets_with_pattern, make_query_pattern

logger = logging.getLogger(__name__)

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

    Usage::

        engine = HybridSearchEngine(config)
        # Index documents (from the indexing pipeline)
        engine.add_document("doc123", "full text here", embedding_vector)
        # Search
        results = await engine.search("my query", query_embedding)
    """

    def __init__(
        self,
        config: Config,
        *,
        alpha: float = 0.5,
        rrf_k: int = 60,
        dimension: int = 384,
        cache_size: int = 256,
    ) -> None:
        """Initialize the hybrid search engine.

        Args:
            config: Application configuration (provides data_dir).
            alpha: Fusion weight. 0.0 = BM25 only, 1.0 = dense only.
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

        # Bounded LRU cache of recently-accessed doc texts for snippets.
        # Cache misses fall back to BM25 index (tantivy) automatically,
        # so ALL texts never need to be resident in RAM simultaneously.
        self._doc_texts: _LRUTextCache = _LRUTextCache(_DOC_TEXT_CACHE_SIZE)

        # LRU result cache — avoids re-running search for repeated queries.
        self._cache: _SearchCache | None = (
            _SearchCache(maxsize=cache_size) if cache_size > 0 else None
        )

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
        self, docs: list[tuple[str, str, np.ndarray]]
    ) -> None:
        """Batch-index documents as (doc_id, text, embedding) triples."""
        if not docs:
            return
        bm25_batch = [(doc_id, text) for doc_id, text, _ in docs]
        dense_batch = [(doc_id, emb) for doc_id, _, emb in docs]

        self.bm25.add_documents(bm25_batch)
        self.dense.add_batch(dense_batch)

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
    ) -> list[SearchResult]:
        """Run hybrid search: BM25 + dense retrieval with RRF fusion.

        This method is async-friendly — it offloads the CPU-bound index
        searches to a thread pool so it can be called from FastAPI handlers.
        Results are cached (LRU) so repeated identical queries are ~0ms.

        Args:
            query: Raw search query string.
            query_embedding: Dense embedding of the query.
            top_k: Number of results to return.
            alpha: Override the default fusion weight for this query.
            max_snippets: Max snippets per result.

        Returns:
            Ranked list of SearchResult objects.
        """
        fusion_alpha = alpha if alpha is not None else self._alpha
        query_norm = query.strip()

        # Fast path: return cached results for this exact query.
        if self._cache:
            cached = self._cache.get(query_norm, top_k, fusion_alpha)
            if cached is not None:
                logger.debug("Cache hit for query %r", query_norm)
                return cached

        loop = asyncio.get_event_loop()

        # Run both searches concurrently in the thread pool
        bm25_future = loop.run_in_executor(
            None, partial(self.bm25.search, query_norm, top_k=top_k * 2)
        )
        dense_future = loop.run_in_executor(
            None, partial(self.dense.search, query_embedding, top_k=top_k * 2)
        )
        bm25_results, dense_results = await asyncio.gather(
            bm25_future, dense_future
        )

        # Fuse results
        fused = weighted_rrf(
            bm25_results, dense_results, alpha=fusion_alpha, k=self._rrf_k
        )

        # Build final results with snippets
        results = self._build_results(query_norm, fused[:top_k], max_snippets)

        if self._cache:
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
    ) -> list[SearchResult]:
        """Synchronous version of search for non-async contexts."""
        fusion_alpha = alpha if alpha is not None else self._alpha
        query_norm = query.strip()

        # Fast path: return cached results for this exact query.
        if self._cache:
            cached = self._cache.get(query_norm, top_k, fusion_alpha)
            if cached is not None:
                return cached

        bm25_results = self.bm25.search(query_norm, top_k=top_k * 2)
        dense_results = self.dense.search(query_embedding, top_k=top_k * 2)

        fused = weighted_rrf(
            bm25_results, dense_results, alpha=fusion_alpha, k=self._rrf_k
        )
        results = self._build_results(query_norm, fused[:top_k], max_snippets)

        if self._cache:
            self._cache.put(query_norm, top_k, fusion_alpha, results)

        return results

    def _build_results(
        self,
        query: str,
        fused: list[FusedResult],
        max_snippets: int,
    ) -> list[SearchResult]:
        """Convert fused results into SearchResult objects with snippets.

        The query pattern is compiled once (and cached globally) then reused
        for every result document, avoiding N redundant re.compile() calls.
        """
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
        """Number of documents in the BM25 index."""
        return self.bm25.doc_count

    @property
    def cache_size(self) -> int:
        """Number of entries currently held in the result cache."""
        return self._cache.size if self._cache else 0

    def set_doc_text(self, doc_id: str, text: str) -> None:
        """Register document text for snippet extraction without re-indexing."""
        self._doc_texts[doc_id] = text
