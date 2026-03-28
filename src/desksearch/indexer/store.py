"""SQLite metadata store for indexed documents and chunks.

Stores document metadata and chunk text for retrieval. Supports checking
whether files need re-indexing based on modification time and content hash.

Thread-safety: a threading.Lock serialises all write operations so the
pipeline (thread-pool) and the API (async) can coexist without corruption.
Reads share the same connection (SQLite WAL mode) and don't hold the lock
so searches are never blocked by concurrent indexing writes.

Error recovery: each file carries an ``indexing_state`` column that is set
to ``'indexing'`` before processing begins and updated to ``'done'`` or
``'failed'`` once finished.  If the process crashes mid-way, the next run
sees ``indexing_state='indexing'`` and re-indexes the file from scratch.
"""
import hashlib
import sqlite3
import threading
import time
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Valid values for the indexing_state column.
STATE_DONE = "done"
STATE_INDEXING = "indexing"
STATE_FAILED = "failed"


def compute_file_hash(path: Path, buf_size: int = 131072) -> str:
    """Compute a fast hash of a file's contents.

    Uses xxhash (XXH3-128) when available (~10x faster than SHA-256),
    falling back to SHA-256 if xxhash is not installed.
    """
    try:
        import xxhash
        h = xxhash.xxh3_128()
    except ImportError:
        h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(buf_size)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


@dataclass
class DocumentRecord:
    """A stored document record."""

    id: int
    path: str
    filename: str
    extension: str
    size: int
    modified_time: float
    indexed_time: float
    num_chunks: int
    indexing_state: str = STATE_DONE
    content_hash: str = ""


@dataclass
class ChunkRecord:
    """A stored chunk record."""

    id: int
    doc_id: int
    text: str
    chunk_index: int
    char_offset: int


class MetadataStore:
    """SQLite-backed store for document and chunk metadata."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        # Serialise all write operations so the pipeline thread-pool and the
        # async API route handlers cannot interleave writes.
        self._write_lock = threading.Lock()
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self.db_path), check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            # WAL mode: concurrent readers don't block writers
            self._conn.execute("PRAGMA journal_mode=WAL")
            # NORMAL sync: safe after WAL, much faster than FULL
            self._conn.execute("PRAGMA synchronous=NORMAL")
            # 64 MB page cache (negative = KB)
            self._conn.execute("PRAGMA cache_size=-65536")
            # Keep temp tables in memory rather than creating temp files
            self._conn.execute("PRAGMA temp_store=MEMORY")
            # Allow OS to mmap up to 256 MB of the DB for read-ahead
            self._conn.execute("PRAGMA mmap_size=268435456")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self) -> None:
        """Create tables and run migrations if needed."""
        with self._write_lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    modified_time REAL NOT NULL,
                    indexed_time REAL NOT NULL,
                    num_chunks INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    char_offset INTEGER NOT NULL,
                    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(path);
                CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
            """)
            self.conn.commit()

            # Migration: add indexing_state column if missing.
            # ALTER TABLE … ADD COLUMN has no IF NOT EXISTS, so we catch the
            # OperationalError that fires when the column already exists.
            try:
                self.conn.execute(
                    f"ALTER TABLE documents ADD COLUMN indexing_state TEXT NOT NULL DEFAULT '{STATE_DONE}'"
                )
                self.conn.commit()
                logger.debug("Migration: added indexing_state column to documents table")
            except sqlite3.OperationalError:
                pass  # Column already exists — nothing to do

            # Migration: add content_hash column for content-based skip.
            try:
                self.conn.execute(
                    "ALTER TABLE documents ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''"
                )
                self.conn.commit()
                logger.debug("Migration: added content_hash column to documents table")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Tables for search history, favorites, and recent opens.
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    result_count INTEGER NOT NULL DEFAULT 0,
                    searched_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS favorites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id INTEGER NOT NULL UNIQUE,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS recent_opens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id INTEGER NOT NULL,
                    opened_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_search_history_time ON search_history(searched_at);
                CREATE INDEX IF NOT EXISTS idx_favorites_doc ON favorites(doc_id);
                CREATE INDEX IF NOT EXISTS idx_recent_opens_time ON recent_opens(opened_at);
            """)
            self.conn.commit()

    # ------------------------------------------------------------------
    # Indexing state management (crash recovery)
    # ------------------------------------------------------------------

    def mark_indexing_started(self, path: Path) -> None:
        """Mark a file as currently being indexed.

        Called before we begin processing a file so that a crash mid-way
        is detectable on the next run (``needs_indexing`` returns True for
        any file whose state is 'indexing').
        """
        now = time.time()
        stat = path.stat()
        with self._write_lock:
            self.conn.execute(
                """INSERT INTO documents
                       (path, filename, extension, size, modified_time, indexed_time,
                        num_chunks, indexing_state)
                   VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                   ON CONFLICT(path) DO UPDATE SET
                       size = excluded.size,
                       modified_time = excluded.modified_time,
                       indexed_time = excluded.indexed_time,
                       indexing_state = excluded.indexing_state""",
                (
                    str(path),
                    path.name,
                    path.suffix.lower(),
                    stat.st_size,
                    stat.st_mtime,
                    now,
                    STATE_INDEXING,
                ),
            )
            self.conn.commit()

    def mark_indexing_done(self, path: Path) -> None:
        """Mark a file's indexing as successfully complete."""
        with self._write_lock:
            self.conn.execute(
                "UPDATE documents SET indexing_state = ? WHERE path = ?",
                (STATE_DONE, str(path)),
            )
            self.conn.commit()

    def mark_indexing_failed(self, path: Path) -> None:
        """Mark a file's indexing as failed so it will be retried next run."""
        with self._write_lock:
            self.conn.execute(
                "UPDATE documents SET indexing_state = ? WHERE path = ?",
                (STATE_FAILED, str(path)),
            )
            self.conn.commit()

    # ------------------------------------------------------------------
    # Core helpers
    # ------------------------------------------------------------------

    def needs_indexing(self, path: Path) -> bool:
        """Return True if the file needs (re-)indexing.

        True when:
        - the file has never been indexed, OR
        - the file was modified since last indexed, OR
        - a previous indexing attempt was interrupted (state='indexing'), OR
        - a previous indexing attempt failed (state='failed').

        Content hash optimisation: if the mtime changed but the content hash
        matches, the file is considered unchanged and skipped.
        """
        row = self.conn.execute(
            "SELECT modified_time, indexing_state, content_hash FROM documents WHERE path = ?",
            (str(path),),
        ).fetchone()
        if row is None:
            return True
        # Crashed mid-way or explicitly failed → always retry
        if row["indexing_state"] in (STATE_INDEXING, STATE_FAILED):
            logger.debug(
                "File %s has state \'%s\' → scheduling re-index",
                path.name,
                row["indexing_state"],
            )
            return True
        try:
            stat = path.stat()
        except OSError:
            return True
        if stat.st_mtime <= row["modified_time"]:
            return False
        # mtime changed — check content hash to avoid unnecessary re-index
        stored_hash = row["content_hash"] if row["content_hash"] else None
        if stored_hash:
            try:
                current_hash = compute_file_hash(path)
                if current_hash == stored_hash:
                    with self._write_lock:
                        self.conn.execute(
                            "UPDATE documents SET modified_time = ? WHERE path = ?",
                            (stat.st_mtime, str(path)),
                        )
                        self.conn.commit()
                    logger.debug(
                        "File %s mtime changed but content hash matches — skipping",
                        path.name,
                    )
                    return False
            except OSError:
                pass
        return True

    def get_document(self, path: Path) -> Optional[DocumentRecord]:
        """Get a document record by path."""
        row = self.conn.execute(
            "SELECT * FROM documents WHERE path = ?",
            (str(path),),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_doc(row)

    def get_document_by_id(self, doc_id: int) -> Optional[DocumentRecord]:
        """Get a document record by ID."""
        row = self.conn.execute(
            "SELECT * FROM documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_doc(row)

    @staticmethod
    def _row_to_doc(row) -> DocumentRecord:
        d = dict(row)
        # indexing_state may be absent in old rows fetched before migration
        d.setdefault("indexing_state", STATE_DONE)
        d.setdefault("content_hash", "")
        return DocumentRecord(**d)

    def upsert_document(
        self,
        path: Path,
        num_chunks: int,
        content_hash: str = "",
    ) -> int:
        """Insert or update a document record. Returns the document ID.

        Sets indexing_state to 'done' on the assumption that upsert is called
        only after chunks have been written.  Use ``mark_indexing_started``
        before you begin processing a file to get crash-recovery semantics.

        Args:
            path: File path.
            num_chunks: Number of chunks produced.
            content_hash: SHA-256 hex digest of file contents.
        """
        stat = path.stat()
        now = time.time()

        with self._write_lock:
            # Delete old chunks if document exists
            existing = self.get_document(path)
            if existing:
                self.conn.execute("DELETE FROM chunks WHERE doc_id = ?", (existing.id,))
                self.conn.execute(
                    """UPDATE documents
                       SET size = ?, modified_time = ?, indexed_time = ?,
                           num_chunks = ?, indexing_state = ?, content_hash = ?
                       WHERE id = ?""",
                    (stat.st_size, stat.st_mtime, now, num_chunks, STATE_DONE,
                     content_hash, existing.id),
                )
                self.conn.commit()
                return existing.id

            cursor = self.conn.execute(
                """INSERT INTO documents
                       (path, filename, extension, size, modified_time, indexed_time,
                        num_chunks, indexing_state, content_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(path),
                    path.name,
                    path.suffix.lower(),
                    stat.st_size,
                    stat.st_mtime,
                    now,
                    num_chunks,
                    STATE_DONE,
                    content_hash,
                ),
            )
            self.conn.commit()
            return cursor.lastrowid

    def add_chunks(self, doc_id: int, chunks: list[tuple[str, int, int]]) -> list[int]:
        """Add chunks for a document.

        Args:
            doc_id: The document ID.
            chunks: List of (text, chunk_index, char_offset) tuples.

        Returns:
            List of chunk IDs (contiguous, in insertion order).
        """
        if not chunks:
            return []
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.executemany(
                "INSERT INTO chunks (doc_id, text, chunk_index, char_offset) VALUES (?, ?, ?, ?)",
                [(doc_id, text, chunk_index, char_offset) for text, chunk_index, char_offset in chunks],
            )
            self.conn.commit()
            # cursor.lastrowid is None after executemany in Python 3.12+ (PEP 249 compliance).
            # Use last_insert_rowid() instead — it's always accurate after a commit.
            last_id: int = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            first_id = last_id - len(chunks) + 1
            return list(range(first_id, last_id + 1))

    def get_chunks(self, doc_id: int) -> list[ChunkRecord]:
        """Get all chunks for a document, ordered by chunk_index."""
        rows = self.conn.execute(
            "SELECT * FROM chunks WHERE doc_id = ? ORDER BY chunk_index",
            (doc_id,),
        ).fetchall()
        return [ChunkRecord(**dict(row)) for row in rows]

    def get_chunk_by_id(self, chunk_id: int) -> Optional[ChunkRecord]:
        """Get a single chunk by ID."""
        row = self.conn.execute(
            "SELECT * FROM chunks WHERE id = ?",
            (chunk_id,),
        ).fetchone()
        if row is None:
            return None
        return ChunkRecord(**dict(row))

    def delete_document(self, path: Path) -> bool:
        """Delete a document and its chunks. Returns True if document existed."""
        existing = self.get_document(path)
        if existing is None:
            return False
        with self._write_lock:
            # Chunks cascade-deleted via foreign key
            self.conn.execute("DELETE FROM documents WHERE id = ?", (existing.id,))
            self.conn.commit()
        return True

    def all_documents(self) -> list[DocumentRecord]:
        """Return all document records."""
        rows = self.conn.execute("SELECT * FROM documents ORDER BY path").fetchall()
        return [self._row_to_doc(row) for row in rows]

    def document_count(self) -> int:
        """Return total number of indexed documents."""
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM documents").fetchone()
        return row["cnt"]

    def chunk_count(self) -> int:
        """Return total number of stored chunks."""
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM chunks").fetchone()
        return row["cnt"]

    def get_documents_by_ids(self, doc_ids: list[int]) -> dict[int, DocumentRecord]:
        """Batch-fetch documents by a list of IDs.

        Returns a dict mapping doc_id → DocumentRecord. Missing IDs are omitted.
        More efficient than N individual ``get_document_by_id`` calls.
        """
        if not doc_ids:
            return {}
        placeholders = ",".join("?" * len(doc_ids))
        rows = self.conn.execute(
            f"SELECT * FROM documents WHERE id IN ({placeholders})",
            doc_ids,
        ).fetchall()
        return {row["id"]: self._row_to_doc(row) for row in rows}

    def get_chunks_by_ids(self, chunk_ids: list[int]) -> dict[int, "ChunkRecord"]:
        """Batch-fetch chunks by a list of IDs.

        Returns a dict mapping chunk_id → ChunkRecord.  Missing IDs are omitted.
        More efficient than N individual ``get_chunk_by_id`` calls.
        """
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" * len(chunk_ids))
        rows = self.conn.execute(
            f"SELECT * FROM chunks WHERE id IN ({placeholders})",
            chunk_ids,
        ).fetchall()
        return {row["id"]: ChunkRecord(**dict(row)) for row in rows}

    def clear_all(self) -> tuple[int, int]:
        """Delete ALL documents and chunks. Returns (docs_deleted, chunks_deleted)."""
        doc_count = self.document_count()
        chunk_count = self.chunk_count()
        with self._write_lock:
            self.conn.execute("DELETE FROM chunks")
            self.conn.execute("DELETE FROM documents")
            self.conn.commit()
        return doc_count, chunk_count

    def delete_documents_by_prefix(self, path_prefix: str) -> int:
        """Delete all documents whose path starts with the given prefix.

        Returns the number of documents deleted.
        """
        rows = self.conn.execute(
            "SELECT id FROM documents WHERE path LIKE ?",
            (f"{path_prefix}%",),
        ).fetchall()
        if not rows:
            return 0
        ids = [r["id"] for r in rows]
        with self._write_lock:
            for doc_id in ids:
                self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            self.conn.commit()
        return len(ids)

    # ------------------------------------------------------------------
    # Search history
    # ------------------------------------------------------------------

    def add_search_history(self, query: str, result_count: int = 0) -> None:
        """Record a search query in history."""
        with self._write_lock:
            self.conn.execute(
                "INSERT INTO search_history (query, result_count, searched_at) VALUES (?, ?, ?)",
                (query, result_count, time.time()),
            )
            self.conn.commit()

    def get_search_history(self, limit: int = 50) -> list[dict]:
        """Return the most recent search queries."""
        rows = self.conn.execute(
            "SELECT query, result_count, searched_at FROM search_history ORDER BY searched_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Favorites
    # ------------------------------------------------------------------

    def add_favorite(self, doc_id: int) -> bool:
        """Add a document to favorites. Returns True if added, False if already exists."""
        with self._write_lock:
            try:
                self.conn.execute(
                    "INSERT INTO favorites (doc_id, created_at) VALUES (?, ?)",
                    (doc_id, time.time()),
                )
                self.conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_favorite(self, doc_id: int) -> bool:
        """Remove a document from favorites. Returns True if removed."""
        with self._write_lock:
            cursor = self.conn.execute(
                "DELETE FROM favorites WHERE doc_id = ?", (doc_id,),
            )
            self.conn.commit()
            return cursor.rowcount > 0

    def get_favorites(self) -> list[dict]:
        """Return all favorited documents with their metadata."""
        rows = self.conn.execute(
            """SELECT f.doc_id, f.created_at, d.path, d.filename, d.extension,
                      d.size, d.modified_time
               FROM favorites f
               JOIN documents d ON f.doc_id = d.id
               ORDER BY f.created_at DESC""",
        ).fetchall()
        return [dict(r) for r in rows]

    def is_favorite(self, doc_id: int) -> bool:
        """Check if a document is favorited."""
        row = self.conn.execute(
            "SELECT 1 FROM favorites WHERE doc_id = ?", (doc_id,),
        ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Recent opens
    # ------------------------------------------------------------------

    def record_open(self, doc_id: int) -> None:
        """Record that a file was opened from search results."""
        with self._write_lock:
            self.conn.execute(
                "INSERT INTO recent_opens (doc_id, opened_at) VALUES (?, ?)",
                (doc_id, time.time()),
            )
            self.conn.commit()

    def get_recent_opens(self, limit: int = 10) -> list[dict]:
        """Return the most recently opened files (deduplicated, most recent first)."""
        rows = self.conn.execute(
            """SELECT r.doc_id, MAX(r.opened_at) as opened_at,
                      d.path, d.filename, d.extension, d.size, d.modified_time
               FROM recent_opens r
               JOIN documents d ON r.doc_id = d.id
               GROUP BY r.doc_id
               ORDER BY opened_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def disk_stats(self) -> dict:
        """Return disk statistics for the database file.

        Returns a dict with:
        - ``db_size_bytes``: total file size on disk
        - ``page_count``: SQLite page count
        - ``freelist_count``: unused pages (reclaimable via VACUUM)
        - ``frag_ratio``: fraction of pages that are free (0.0–1.0)
        """
        try:
            page_count = self.conn.execute("PRAGMA page_count").fetchone()[0]
            freelist = self.conn.execute("PRAGMA freelist_count").fetchone()[0]
            page_size = self.conn.execute("PRAGMA page_size").fetchone()[0]
        except Exception:
            return {
                "db_size_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0,
                "page_count": 0,
                "freelist_count": 0,
                "frag_ratio": 0.0,
            }

        db_size = page_count * page_size
        frag = freelist / page_count if page_count > 0 else 0.0
        return {
            "db_size_bytes": db_size,
            "page_count": page_count,
            "freelist_count": freelist,
            "frag_ratio": frag,
        }

    def vacuum_if_fragmented(self, threshold: float = 0.1) -> bool:
        """Run VACUUM if the database is more than *threshold* fragmented.

        Returns True if VACUUM was performed.
        """
        stats = self.disk_stats()
        if stats["frag_ratio"] < threshold:
            return False
        logger.info(
            "SQLite fragmentation %.1f%% exceeds %.0f%% threshold — running VACUUM",
            stats["frag_ratio"] * 100,
            threshold * 100,
        )
        with self._write_lock:
            self.conn.execute("VACUUM")
        return True

    def ping(self) -> bool:
        """Return True if the database connection is healthy."""
        try:
            self.conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
