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
from collections import OrderedDict
from pathlib import Path
from typing import Optional

# Maximum number of pre-parsed tantivy queries to keep in RAM.
# parse_query is fast but not free; caching avoids re-parsing identical
# queries on every search call (very common in paginated / repeat scenarios).
_QUERY_CACHE_SIZE = 256

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


# ---------------------------------------------------------------------------
# CJK support
# ---------------------------------------------------------------------------
# tantivy's default tokenizer splits on non-alphanumeric characters, so an
# unspaced Chinese sentence such as "第三季度营收报告" becomes ONE token and can
# never match a shorter query like "季度营收" — every Chinese query then falls
# back to the (noisy) dense index. Indexing the character bigrams of each CJK
# run is the classic solution: the query is turned into bigrams the same way,
# so "季度营收" matches inside "第三季度营收报告" (季度/度营/营收 all hit).
_CJK_RANGES: tuple[tuple[int, int], ...] = (
    (0x2E80, 0x2EFF),    # CJK radicals
    (0x3040, 0x30FF),    # Hiragana + Katakana
    (0x3400, 0x4DBF),    # CJK ext A
    (0x4E00, 0x9FFF),    # CJK unified
    (0xAC00, 0xD7AF),    # Hangul syllables
    (0xF900, 0xFAFF),    # CJK compatibility
    (0x20000, 0x2FA1F),  # CJK ext B+
)


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _CJK_RANGES)


def cjk_bigrams(text: str) -> str:
    """Return space-separated bigrams for every CJK run in *text*.

    Non-CJK text is ignored (it is handled by the normal tokenizer). A CJK run
    of a single character contributes that character, so one-character queries
    still work. The result is a plain token string that tantivy's default
    tokenizer splits correctly.
    """
    tokens: list[str] = []
    run: list[str] = []

    def flush() -> None:
        if not run:
            return
        if len(run) == 1:
            tokens.append(run[0])
        else:
            tokens.extend(run[i] + run[i + 1] for i in range(len(run) - 1))
        run.clear()

    for ch in text:
        if _is_cjk(ch):
            run.append(ch)
        else:
            flush()
    flush()
    return " ".join(tokens)



# Bump when the tantivy schema changes: the index moves to a new directory
# instead of being migrated in place. An in-place rename fails on Windows
# (""[WinError 5] access denied") because the failed open leaves handles on the
# old files, which used to disable BM25 for the whole session.
BM25_SCHEMA_VERSION = 2  # v2 = added body_cjk (CJK bigram support)
BM25_DIR_NAME = f"bm25-v{BM25_SCHEMA_VERSION}"
LEGACY_BM25_DIR_NAME = "bm25"


def bm25_index_dir(data_dir: Path) -> Path:
    """Canonical BM25 index directory inside *data_dir*."""
    return Path(data_dir) / BM25_DIR_NAME


class BM25Index:
    """Tantivy-backed BM25 full-text search index.

    Stores documents with a doc_id (string) and body text.
    Persists to disk so the index survives restarts.

    ``available`` is False when tantivy is missing or the index is
    irrecoverably corrupt.  Callers should fall back to dense-only search.
    """

    def __init__(self, data_dir: Path) -> None:
        data_dir = Path(data_dir)
        self._index_dir = bm25_index_dir(data_dir)
        self._index_dir.mkdir(parents=True, exist_ok=True)

        # Serialise write operations — tantivy's Python binding doesn't
        # guarantee thread-safety for concurrent writers.
        self._write_lock = threading.Lock()

        # LRU cache for pre-parsed tantivy Query objects.
        # Keyed on the raw query string; avoids re-parsing for repeated queries.
        self._query_cache: OrderedDict[str, object] = OrderedDict()
        self._query_cache_lock = threading.Lock()

        self.available: bool = _TANTIVY_AVAILABLE
        self._index: Optional[tantivy.Index] = None
        # True when a fresh index directory was created for a data dir that
        # already had an older index; _warm_search_engine() refills it from the
        # SQLite store so no full re-index is needed.
        self.schema_reset: bool = False

        if self.available:
            self._schema = self._build_schema()
            empty_dir = not any(self._index_dir.iterdir())
            legacy_exists = (data_dir / LEGACY_BM25_DIR_NAME).is_dir()
            try:
                self._index = tantivy.Index(self._schema, path=str(self._index_dir))
                if empty_dir and legacy_exists:
                    self.schema_reset = True
                    logger.info(
                        "BM25 schema upgraded to v%d (%s); the previous index in "
                        "%s is no longer used and will be refilled from the store.",
                        BM25_SCHEMA_VERSION,
                        self._index_dir.name,
                        LEGACY_BM25_DIR_NAME,
                    )
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
        # Bigram tokens for CJK text (indexed only — never stored/displayed).
        builder.add_text_field("body_cjk")
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
                writer.add_document(
                    tantivy.Document(doc_id=doc_id, body=body, body_cjk=cjk_bigrams(body))
                )
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
            self._invalidate_query_cache()

    def add_documents(self, docs: list[tuple[str, str]]) -> None:
        """Batch-add documents as (doc_id, body) pairs."""
        if not docs or not self.available or self._index is None:
            return
        with self._write_lock:
            writer = self._index.writer()
            try:
                for doc_id, body in docs:
                    writer.delete_documents("doc_id", doc_id)
                    writer.add_document(
                        tantivy.Document(doc_id=doc_id, body=body, body_cjk=cjk_bigrams(body))
                    )
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
            self._invalidate_query_cache()

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
            self._invalidate_query_cache()

    # ------------------------------------------------------------------
    # Query cache helpers
    # ------------------------------------------------------------------

    def _get_cached_query(self, query: str):
        """Return a cached parsed tantivy Query, or None on cache miss."""
        with self._query_cache_lock:
            if query in self._query_cache:
                self._query_cache.move_to_end(query)
                return self._query_cache[query]
        return None

    def _put_cached_query(self, query: str, parsed) -> None:
        """Store a parsed tantivy Query in the LRU cache."""
        with self._query_cache_lock:
            self._query_cache[query] = parsed
            self._query_cache.move_to_end(query)
            while len(self._query_cache) > _QUERY_CACHE_SIZE:
                self._query_cache.popitem(last=False)

    def _invalidate_query_cache(self) -> None:
        """Clear the query cache after any index mutation (add/delete)."""
        with self._query_cache_lock:
            self._query_cache.clear()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _build_query(self, query: str):
        """Parse *query* into a tantivy Query, adding a CJK bigram branch.

        The raw query is matched against ``body`` (works for Latin scripts and
        for CJK runs that appear verbatim). When the query contains CJK, its
        bigrams are additionally matched against ``body_cjk``, which is what
        makes partial Chinese queries hit.
        """
        primary = self._index.parse_query(query, ["body"])

        bigrams = cjk_bigrams(query)
        if not bigrams:
            return primary

        cjk_query = self._index.parse_query(bigrams, ["body_cjk"])
        return tantivy.Query.boolean_query(
            [(tantivy.Occur.Should, primary), (tantivy.Occur.Should, cjk_query)]
        )

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Search the index, returning a list of (doc_id, score) tuples.

        Returns an empty list (rather than raising) on any error.
        Parsed queries are cached in an LRU to avoid re-parsing identical strings.
        """
        if not self.available or self._index is None:
            return []
        if not query.strip():
            return []

        try:
            searcher = self._index.searcher()
            parsed_query = self._get_cached_query(query)
            if parsed_query is None:
                parsed_query = self._build_query(query)
                self._put_cached_query(query, parsed_query)
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
