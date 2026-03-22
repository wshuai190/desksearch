"""BM25 index wrapper using tantivy-py for fast full-text search."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import tantivy

logger = logging.getLogger(__name__)


class BM25Index:
    """Tantivy-backed BM25 full-text search index.

    Stores documents with a doc_id (string) and body text.
    Persists to disk so the index survives restarts.
    """

    def __init__(self, data_dir: Path) -> None:
        self._index_dir = data_dir / "bm25"
        self._index_dir.mkdir(parents=True, exist_ok=True)

        self._schema = self._build_schema()
        self._index = tantivy.Index(self._schema, path=str(self._index_dir))

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
        writer = self._index.writer()
        try:
            # Delete any existing document with the same doc_id first.
            writer.delete_documents("doc_id", doc_id)
            writer.add_document(tantivy.Document(doc_id=doc_id, body=body))
            writer.commit()
        except Exception:
            writer.rollback()
            raise
        self._index.reload()

    def add_documents(self, docs: list[tuple[str, str]]) -> None:
        """Batch-add documents as (doc_id, body) pairs."""
        if not docs:
            return
        writer = self._index.writer()
        try:
            for doc_id, body in docs:
                writer.delete_documents("doc_id", doc_id)
                writer.add_document(tantivy.Document(doc_id=doc_id, body=body))
            writer.commit()
        except Exception:
            writer.rollback()
            raise
        self._index.reload()

    def delete_document(self, doc_id: str) -> None:
        """Remove a document by doc_id."""
        writer = self._index.writer()
        try:
            writer.delete_documents("doc_id", doc_id)
            writer.commit()
        except Exception:
            writer.rollback()
            raise
        self._index.reload()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Search the index, returning a list of (doc_id, score) tuples.

        Returns results sorted by descending BM25 score.
        """
        if not query.strip():
            return []

        searcher = self._index.searcher()
        parsed_query = self._index.parse_query(query, ["body"])

        try:
            results = searcher.search(parsed_query, top_k).hits
        except Exception as exc:
            logger.warning("BM25 search failed for query %r: %s", query, exc)
            return []

        scored: list[tuple[str, float]] = []
        for score, best_doc_address in results:
            doc = searcher.doc(best_doc_address)
            doc_id = doc["doc_id"][0]
            scored.append((doc_id, float(score)))

        return scored

    def get_document(self, doc_id: str) -> Optional[str]:
        """Retrieve the body text for a specific doc_id, or None."""
        searcher = self._index.searcher()
        query = self._index.parse_query(f'"{doc_id}"', ["doc_id"])
        results = searcher.search(query, 1).hits
        if not results:
            return None
        _, addr = results[0]
        doc = searcher.doc(addr)
        return doc["body"][0]

    @property
    def doc_count(self) -> int:
        """Return the number of documents in the index."""
        return self._index.searcher().num_docs
