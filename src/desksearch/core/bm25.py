"""BM25 index wrapper using tantivy-py for fast full-text search.

Thread-safety: write operations (add / delete) acquire a threading.Lock.
tantivy itself serialises index writers, but the Python binding can raise
concurrency errors without explicit locking; the lock makes it safe.

Graceful degradation: if tantivy is unavailable or the index directory is
corrupt, ``BM25Index`` sets ``self.available = False`` and all methods
return safe empty results rather than raising.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import tantivy
    _TANTIVY_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TANTIVY_AVAILABLE = False
    logger.error(
        "tantivy-py is not installed — BM25 search will be unavailable. "
        "Install with: pip install tantivy"
    )


class BM25Index:
    """Tantivy-backed BM25 full-text search index.

    Stores documents with a doc_id (string) and body text.
    Persists to disk so the index survives restarts.

    ``available`` is False when tantivy is missing or the index is
    irrecoverably corrupt.  Callers should fall back to dense-only search.
    """

    def __init__(self, data_dir: Path) -> None:
        self._index_dir = data_dir / "bm25"
        self._index_dir.mkdir(parents=True, exist_ok=True)

        # Serialise write operations — tantivy's Python binding doesn't
        # guarantee thread-safety for concurrent writers.
        self._write_lock = threading.Lock()

        self.available: bool = _TANTIVY_AVAILABLE
        self._index: Optional[tantivy.Index] = None

        if self.available:
            self._schema = self._build_schema()
            try:
                self._index = tantivy.Index(self._schema, path=str(self._index_dir))
            except Exception as exc:
                logger.error(
                    "Failed to open BM25 index at %s (corrupt?): %s. "
                    "BM25 search will be unavailable for this session.",
                    self._index_dir,
                    exc,
                    exc_info=True,
                )
                self.available = False

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    @staticmethod
    def _build_schema() -> tantivy.SchemaBuilder:
        builder = tantivy.SchemaBuilder()
        builder.add_text_field("doc_id", stored=True)
        builder.add_text_field("body", stored=True)
        return builder.build()

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def add_document(self, doc_id: str, body: str) -> None:
        """Add or update a single document in the index."""
        if not self.available or self._index is None:
            return
        with self._write_lock:
            writer = self._index.writer()
            try:
                writer.delete_documents("doc_id", doc_id)
                writer.add_document(tantivy.Document(doc_id=doc_id, body=body))
                writer.commit()
            except Exception as exc:
                logger.error("BM25 add_document failed for %r: %s", doc_id, exc)
                try:
                    writer.rollback()
                except Exception:
                    pass
                return
            try:
                self._index.reload()
            except Exception as exc:
                logger.warning("BM25 reload failed after add_document: %s", exc)

    def add_documents(self, docs: list[tuple[str, str]]) -> None:
        """Batch-add documents as (doc_id, body) pairs."""
        if not docs or not self.available or self._index is None:
            return
        with self._write_lock:
            writer = self._index.writer()
            try:
                for doc_id, body in docs:
                    writer.delete_documents("doc_id", doc_id)
                    writer.add_document(tantivy.Document(doc_id=doc_id, body=body))
                writer.commit()
            except Exception as exc:
                logger.error("BM25 add_documents batch failed: %s", exc)
                try:
                    writer.rollback()
                except Exception:
                    pass
                return
            try:
                self._index.reload()
            except Exception as exc:
                logger.warning("BM25 reload failed after add_documents: %s", exc)

    def delete_document(self, doc_id: str) -> None:
        """Remove a document by doc_id."""
        if not self.available or self._index is None:
            return
        with self._write_lock:
            writer = self._index.writer()
            try:
                writer.delete_documents("doc_id", doc_id)
                writer.commit()
            except Exception as exc:
                logger.error("BM25 delete_document failed for %r: %s", doc_id, exc)
                try:
                    writer.rollback()
                except Exception:
                    pass
                return
            try:
                self._index.reload()
            except Exception as exc:
                logger.warning("BM25 reload failed after delete_document: %s", exc)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Search the index, returning a list of (doc_id, score) tuples.

        Returns an empty list (rather than raising) on any error.
        """
        if not self.available or self._index is None:
            return []
        if not query.strip():
            return []

        try:
            searcher = self._index.searcher()
            parsed_query = self._index.parse_query(query, ["body"])
            results = searcher.search(parsed_query, top_k).hits
        except Exception as exc:
            logger.warning("BM25 search failed for query %r: %s", query, exc)
            return []

        scored: list[tuple[str, float]] = []
        for score, best_doc_address in results:
            try:
                doc = searcher.doc(best_doc_address)
                doc_id = doc["doc_id"][0]
                scored.append((doc_id, float(score)))
            except Exception as exc:
                logger.warning("BM25 result fetch failed: %s", exc)
                continue

        return scored

    def get_document(self, doc_id: str) -> Optional[str]:
        """Retrieve the body text for a specific doc_id, or None."""
        if not self.available or self._index is None:
            return None
        try:
            searcher = self._index.searcher()
            query = self._index.parse_query(f'"{doc_id}"', ["doc_id"])
            results = searcher.search(query, 1).hits
            if not results:
                return None
            _, addr = results[0]
            doc = searcher.doc(addr)
            return doc["body"][0]
        except Exception as exc:
            logger.warning("BM25 get_document failed for %r: %s", doc_id, exc)
            return None

    @property
    def doc_count(self) -> int:
        """Return the number of documents in the index."""
        if not self.available or self._index is None:
            return 0
        try:
            return self._index.searcher().num_docs
        except Exception:
            return 0
