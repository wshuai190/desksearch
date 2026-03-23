"""Search analytics and suggestion tracking via SQLite.

Tracks:
- Recent searches (for suggestions and analytics)
- Result clicks (for popular files analytics)
- Aggregated search frequency

All operations are synchronous and thread-safe via a write lock.
"""
from __future__ import annotations

import sqlite3
import threading
import time
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AnalyticsStore:
    """SQLite-backed store for search analytics and recent searches."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._write_lock = threading.Lock()
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA cache_size=-16384")
        return self._conn

    def _init_db(self) -> None:
        with self._write_lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    result_count INTEGER NOT NULL DEFAULT 0,
                    searched_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS clicks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    doc_path TEXT NOT NULL,
                    doc_filename TEXT NOT NULL,
                    clicked_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_searches_query ON searches(query);
                CREATE INDEX IF NOT EXISTS idx_searches_at ON searches(searched_at);
                CREATE INDEX IF NOT EXISTS idx_clicks_at ON clicks(clicked_at);
                CREATE INDEX IF NOT EXISTS idx_clicks_path ON clicks(doc_path);
            """)
            self.conn.commit()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_search(self, query: str, result_count: int = 0) -> None:
        """Record a search query."""
        query = query.strip()
        if not query or len(query) < 2:
            return
        with self._write_lock:
            self.conn.execute(
                "INSERT INTO searches (query, result_count, searched_at) VALUES (?, ?, ?)",
                (query, result_count, time.time()),
            )
            self.conn.commit()

    def record_click(self, query: str, doc_path: str, doc_filename: str) -> None:
        """Record a click on a search result."""
        query = query.strip()
        if not query:
            return
        with self._write_lock:
            self.conn.execute(
                "INSERT INTO clicks (query, doc_path, doc_filename, clicked_at) VALUES (?, ?, ?, ?)",
                (query, doc_path, doc_filename, time.time()),
            )
            self.conn.commit()

    # ------------------------------------------------------------------
    # Suggestions
    # ------------------------------------------------------------------

    def get_recent_searches(self, limit: int = 20) -> list[str]:
        """Return recent unique searches (most recent first)."""
        rows = self.conn.execute(
            """
            SELECT query FROM (
                SELECT query, MAX(searched_at) as last_at
                FROM searches
                GROUP BY LOWER(query)
                ORDER BY last_at DESC
                LIMIT ?
            )
            """,
            (limit,),
        ).fetchall()
        return [r["query"] for r in rows]

    def get_frequent_searches(self, limit: int = 20) -> list[tuple[str, int]]:
        """Return (query, count) for most frequent searches."""
        rows = self.conn.execute(
            """
            SELECT LOWER(query) as q, COUNT(*) as cnt
            FROM searches
            GROUP BY LOWER(query)
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [(r["q"], r["cnt"]) for r in rows]

    def suggest_from_recent(self, prefix: str, limit: int = 5) -> list[str]:
        """Return recent searches matching a prefix (case-insensitive)."""
        prefix_lower = prefix.lower()
        rows = self.conn.execute(
            """
            SELECT query FROM (
                SELECT query, MAX(searched_at) as last_at
                FROM searches
                WHERE LOWER(query) LIKE ?
                GROUP BY LOWER(query)
                ORDER BY last_at DESC
                LIMIT ?
            )
            """,
            (f"{prefix_lower}%", limit),
        ).fetchall()
        return [r["query"] for r in rows]

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def top_searches(self, limit: int = 10, days: int = 30) -> list[dict]:
        """Return top searches in the last N days."""
        since = time.time() - days * 86400
        rows = self.conn.execute(
            """
            SELECT LOWER(query) as query, COUNT(*) as count,
                   AVG(result_count) as avg_results
            FROM searches
            WHERE searched_at >= ?
            GROUP BY LOWER(query)
            ORDER BY count DESC
            LIMIT ?
            """,
            (since, limit),
        ).fetchall()
        return [{"query": r["query"], "count": r["count"], "avg_results": round(r["avg_results"] or 0, 1)} for r in rows]

    def top_clicked_files(self, limit: int = 10, days: int = 30) -> list[dict]:
        """Return most clicked files in the last N days."""
        since = time.time() - days * 86400
        rows = self.conn.execute(
            """
            SELECT doc_path, doc_filename, COUNT(*) as clicks
            FROM clicks
            WHERE clicked_at >= ?
            GROUP BY doc_path
            ORDER BY clicks DESC
            LIMIT ?
            """,
            (since, limit),
        ).fetchall()
        return [{"path": r["doc_path"], "filename": r["doc_filename"], "clicks": r["clicks"]} for r in rows]

    def search_frequency_over_time(self, days: int = 30, bucket: str = "day") -> list[dict]:
        """Return search counts grouped by day over the last N days."""
        since = time.time() - days * 86400
        rows = self.conn.execute(
            """
            SELECT date(datetime(searched_at, 'unixepoch')) as day,
                   COUNT(*) as count
            FROM searches
            WHERE searched_at >= ?
            GROUP BY day
            ORDER BY day
            """,
            (since,),
        ).fetchall()
        return [{"date": r["day"], "count": r["count"]} for r in rows]

    def total_searches(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as n FROM searches").fetchone()
        return row["n"] if row else 0

    def total_clicks(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as n FROM clicks").fetchone()
        return row["n"] if row else 0
