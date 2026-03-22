"""Hybrid search engine combining BM25 and dense retrieval."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from functools import partial
from typing import Optional

import numpy as np

from desksearch.config import Config
from desksearch.core.bm25 import BM25Index
from desksearch.core.dense import DenseIndex
from desksearch.core.fusion import FusedResult, weighted_rrf
from desksearch.core.snippets import Snippet, extract_snippets

logger = logging.getLogger(__name__)


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
    ) -> None:
        """Initialize the hybrid search engine.

        Args:
            config: Application configuration (provides data_dir).
            alpha: Fusion weight. 0.0 = BM25 only, 1.0 = dense only.
            rrf_k: RRF constant.
            dimension: Embedding vector dimension.
        """
        self._config = config
        self._alpha = alpha
        self._rrf_k = rrf_k

        self.bm25 = BM25Index(config.data_dir)
        self.dense = DenseIndex(config.data_dir, dimension=dimension)

        # In-memory cache of doc texts for snippet extraction.
        # In production this would be backed by the SQLite metadata store.
        self._doc_texts: dict[str, str] = {}

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

    def delete_document(self, doc_id: str) -> None:
        """Remove a document from all indexes."""
        self.bm25.delete_document(doc_id)
        self.dense.delete(doc_id)
        self._doc_texts.pop(doc_id, None)

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

        Args:
            query: Raw search query string.
            query_embedding: Dense embedding of the query.
            top_k: Number of results to return.
            alpha: Override the default fusion weight for this query.
            max_snippets: Max snippets per result.

        Returns:
            Ranked list of SearchResult objects.
        """
        loop = asyncio.get_event_loop()
        fusion_alpha = alpha if alpha is not None else self._alpha

        # Run both searches concurrently in the thread pool
        bm25_future = loop.run_in_executor(
            None, partial(self.bm25.search, query, top_k=top_k * 2)
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
        return self._build_results(query, fused[:top_k], max_snippets)

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

        bm25_results = self.bm25.search(query, top_k=top_k * 2)
        dense_results = self.dense.search(query_embedding, top_k=top_k * 2)

        fused = weighted_rrf(
            bm25_results, dense_results, alpha=fusion_alpha, k=self._rrf_k
        )
        return self._build_results(query, fused[:top_k], max_snippets)

    def _build_results(
        self,
        query: str,
        fused: list[FusedResult],
        max_snippets: int,
    ) -> list[SearchResult]:
        """Convert fused results into SearchResult objects with snippets."""
        results: list[SearchResult] = []
        for fr in fused:
            text = self._doc_texts.get(fr.doc_id) or self.bm25.get_document(fr.doc_id)
            snippets: list[Snippet] = []
            if text:
                snippets = extract_snippets(text, query, max_snippets=max_snippets)

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

    def set_doc_text(self, doc_id: str, text: str) -> None:
        """Register document text for snippet extraction without re-indexing."""
        self._doc_texts[doc_id] = text
