"""SQLite metadata store for indexed documents and chunks.

Stores document metadata and chunk text for retrieval. Supports checking
whether files need re-indexing based on modification time.
"""
import sqlite3
import time
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


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
        """Create tables if they don't exist."""
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

    def needs_indexing(self, path: Path) -> bool:
        """Check if a file needs (re-)indexing based on modification time."""
        row = self.conn.execute(
            "SELECT modified_time FROM documents WHERE path = ?",
            (str(path),),
        ).fetchone()
        if row is None:
            return True
        return path.stat().st_mtime > row["modified_time"]

    def get_document(self, path: Path) -> Optional[DocumentRecord]:
        """Get a document record by path."""
        row = self.conn.execute(
            "SELECT * FROM documents WHERE path = ?",
            (str(path),),
        ).fetchone()
        if row is None:
            return None
        return DocumentRecord(**dict(row))

    def get_document_by_id(self, doc_id: int) -> Optional[DocumentRecord]:
        """Get a document record by ID."""
        row = self.conn.execute(
            "SELECT * FROM documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
        if row is None:
            return None
        return DocumentRecord(**dict(row))

    def upsert_document(
        self,
        path: Path,
        num_chunks: int,
    ) -> int:
        """Insert or update a document record. Returns the document ID."""
        stat = path.stat()
        now = time.time()

        # Delete old chunks if document exists
        existing = self.get_document(path)
        if existing:
            self.conn.execute("DELETE FROM chunks WHERE doc_id = ?", (existing.id,))
            self.conn.execute(
                """UPDATE documents
                   SET size = ?, modified_time = ?, indexed_time = ?, num_chunks = ?
                   WHERE id = ?""",
                (stat.st_size, stat.st_mtime, now, num_chunks, existing.id),
            )
            self.conn.commit()
            return existing.id

        cursor = self.conn.execute(
            """INSERT INTO documents (path, filename, extension, size, modified_time, indexed_time, num_chunks)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                str(path),
                path.name,
                path.suffix.lower(),
                stat.st_size,
                stat.st_mtime,
                now,
                num_chunks,
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
        # Chunks cascade-deleted via foreign key
        self.conn.execute("DELETE FROM documents WHERE id = ?", (existing.id,))
        self.conn.commit()
        return True

    def all_documents(self) -> list[DocumentRecord]:
        """Return all document records."""
        rows = self.conn.execute("SELECT * FROM documents ORDER BY path").fetchall()
        return [DocumentRecord(**dict(row)) for row in rows]

    def document_count(self) -> int:
        """Return total number of indexed documents."""
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM documents").fetchone()
        return row["cnt"]

    def chunk_count(self) -> int:
        """Return total number of stored chunks."""
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM chunks").fetchone()
        return row["cnt"]

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

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
