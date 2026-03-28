"""DeskSearch Python SDK.

Provides a high-level :class:`DeskSearch` class for embedding DeskSearch
search and indexing capabilities directly into Python applications.

Example::

    from desksearch import DeskSearch

    ds = DeskSearch("~/.desksearch")
    results = ds.search("quarterly report", limit=5)
    for r in results:
        print(r.rank, r.filename, r.score)
        print(" ", r.path)
        print(" ", r.snippet)

    # Index a folder
    stats = ds.index("~/Documents")
    print(f"Indexed {stats['indexed']} files")

    # System info
    info = ds.info()
    print(f"{info['documents']} documents, {info['disk_usage_mb']:.1f} MB")
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator, Iterator


@dataclass
class SearchResult:
    """A single search result returned by :meth:`DeskSearch.search`.

    Attributes:
        rank: 1-based position in the result list.
        filename: Base name of the matched file (e.g. ``"report.pdf"``).
        path: Absolute path to the matched file.
        extension: File extension without leading dot (e.g. ``"pdf"``).
        score: Relevance score — higher is more relevant.
        snippet: A text excerpt from the matched passage.
        chunk_id: Internal chunk ID in the metadata store.
        doc_id: Internal document ID in the metadata store.
    """
    rank: int
    filename: str
    path: str
    extension: str
    score: float
    snippet: str
    chunk_id: int = 0
    doc_id: int = 0

    def __repr__(self) -> str:
        return (
            f"SearchResult(rank={self.rank}, filename={self.filename!r}, "
            f"score={self.score:.4f})"
        )


class DeskSearch:
    """High-level API for DeskSearch.

    Parameters:
        data_dir: Path to the DeskSearch data directory.
                  Defaults to ``~/.desksearch``.  The directory is
                  created automatically if it does not exist.

    Example::

        from desksearch import DeskSearch

        ds = DeskSearch()
        results = ds.search("machine learning papers")
        for r in results:
            print(r.path, r.score)
    """

    def __init__(self, data_dir: str | Path | None = None) -> None:
        from desksearch.config import Config, DEFAULT_DATA_DIR

        if data_dir is None:
            self._config = Config.load()
        else:
            resolved = Path(data_dir).expanduser().resolve()
            # Load existing config but override data_dir
            try:
                self._config = Config.load(resolved / "config.json")
            except Exception:
                self._config = Config(data_dir=resolved)

        self._config.data_dir.mkdir(parents=True, exist_ok=True)
        self._engine = None
        self._embedder = None
        self._store = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_store(self):
        if self._store is None:
            from desksearch.indexer.store import MetadataStore
            self._store = MetadataStore(self._config.data_dir / "metadata.db")
        return self._store

    def _get_embedder(self):
        if self._embedder is None:
            from desksearch.indexer.embedder import Embedder
            self._config.resolve_starbucks_tier()
            self._embedder = Embedder(
                self._config.embedding_model,
                embedding_dim=self._config.embedding_dim,
                embedding_layers=self._config.embedding_layers,
            )
        return self._embedder

    def _get_engine(self):
        if self._engine is None:
            from desksearch.core.search import HybridSearchEngine
            from desksearch.api.server import _warm_search_engine
            self._engine = HybridSearchEngine(self._config)
            _warm_search_engine(
                self._engine,
                self._get_store(),
                self._config,
            )
        return self._engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        file_type: str | None = None,
    ) -> list[SearchResult]:
        """Search the index and return ranked results.

        Parameters:
            query: Natural language or keyword search string.
            limit: Maximum number of results to return (default 10).
            file_type: Optional file extension filter without leading dot
                       (e.g. ``"pdf"``, ``"md"``, ``"py"``).

        Returns:
            A list of :class:`SearchResult` objects sorted by relevance
            (highest score first).

        Example::

            results = ds.search("budget spreadsheet", limit=5, file_type="xlsx")
        """
        store = self._get_store()
        embedder = self._get_embedder()
        engine = self._get_engine()

        query_embedding = embedder.embed_query(query)
        raw = engine.search_sync(query, query_embedding, top_k=limit * 2)

        results: list[SearchResult] = []
        for r in raw:
            try:
                chunk_id = int(r.doc_id)
            except (ValueError, TypeError):
                continue

            chunk = store.get_chunk_by_id(chunk_id)
            if chunk is None:
                continue

            doc = store.get_document_by_id(chunk.doc_id)
            if doc is None:
                continue

            ext = doc.extension.lstrip(".")
            if file_type and ext != file_type:
                continue

            snippet = r.snippets[0].text if r.snippets else chunk.text[:200]
            results.append(SearchResult(
                rank=len(results) + 1,
                filename=doc.filename,
                path=str(doc.path),
                extension=ext,
                score=r.score,
                snippet=snippet,
                chunk_id=chunk_id,
                doc_id=chunk.doc_id,
            ))

            if len(results) >= limit:
                break

        return results

    def index(
        self,
        path: str | Path,
        *,
        verbose: bool = False,
    ) -> dict:
        """Index a file or directory.

        Parameters:
            path: Path to a file or directory to index.
            verbose: If True, print progress to stdout.

        Returns:
            A dict with keys ``indexed``, ``skipped``, ``errors``,
            ``total_documents``, ``total_chunks``.

        Example::

            stats = ds.index("~/Documents/Papers")
            print(f"Indexed {stats['indexed']} new files")
        """
        from desksearch.core.search import HybridSearchEngine
        from desksearch.indexer.pipeline import IndexingPipeline, StatusType

        resolved = Path(path).expanduser().resolve()
        engine = HybridSearchEngine(self._config)
        pipeline = IndexingPipeline(self._config, search_engine=engine)

        stats = {"indexed": 0, "skipped": 0, "errors": 0}

        try:
            gen = (
                pipeline.index_directory(resolved)
                if resolved.is_dir()
                else pipeline.index_file(resolved)
            )
            try:
                while True:
                    status = next(gen)
                    if status.status == StatusType.COMPLETE and status.file:
                        stats["indexed"] += 1
                        if verbose:
                            print(f"  OK  {status.file}")
                    elif status.status == StatusType.ERROR:
                        stats["errors"] += 1
                        if verbose:
                            print(f"  ERR {status.file}: {status.message}")
                    elif status.status == StatusType.SKIPPED:
                        stats["skipped"] += 1
            except StopIteration:
                pass

            stats["total_documents"] = pipeline.store.document_count()
            stats["total_chunks"] = pipeline.store.chunk_count()

            # Invalidate cached engine so next search uses fresh data
            self._engine = None

        finally:
            pipeline.close()

        return stats

    def info(self) -> dict:
        """Return index statistics as a dictionary.

        Returns:
            A dict with keys: ``documents``, ``chunks``, ``disk_usage_mb``,
            ``data_dir``, ``embedding_model``, ``watched_folders``.

        Example::

            info = ds.info()
            print(f"Total: {info['documents']} documents, {info['disk_usage_mb']:.1f} MB")
        """
        store = self._get_store()
        doc_count = store.document_count()
        chunk_count = store.chunk_count()

        total_bytes = 0
        if self._config.data_dir.exists():
            total_bytes = sum(
                f.stat().st_size
                for f in self._config.data_dir.rglob("*")
                if f.is_file()
            )

        return {
            "documents": doc_count,
            "chunks": chunk_count,
            "disk_usage_mb": round(total_bytes / (1024 * 1024), 2),
            "data_dir": str(self._config.data_dir),
            "embedding_model": self._config.embedding_model,
            "watched_folders": [str(p) for p in self._config.index_paths],
        }

    def close(self) -> None:
        """Release resources held by this instance.

        Call this when you are done using the SDK object, especially in
        long-running scripts, to close database connections and free memory.
        """
        if self._store is not None:
            try:
                self._store.close()
            except Exception:
                pass
            self._store = None
        self._engine = None
        self._embedder = None

    def __enter__(self) -> "DeskSearch":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"DeskSearch(data_dir={str(self._config.data_dir)!r})"
