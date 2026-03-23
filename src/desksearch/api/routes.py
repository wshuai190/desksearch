"""FastAPI route definitions for DeskSearch."""
import asyncio
import logging
import math
import platform
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, HTTPException

from desksearch.api.schemas import (
    ActivityEntry,
    ActivityResponse,
    AnalyticsSummary,
    CollectionsResponse,
    DashboardStats,
    DuplicatePair,
    DuplicatesResponse,
    ErrorResponse,
    FileInfo,
    FilePreview,
    FilesResponse,
    FolderAddRequest,
    FolderInfo,
    IndexRequest,
    IndexStatus,
    NLAnswer,
    RichPreview,
    RichSearchResponse,
    RichSearchResult,
    SearchResponse,
    SearchResult,
    SettingsResponse,
    SettingsUpdateRequest,
    SuggestResponse,
    TopicInfo,
)
from desksearch.config import Config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Module-level state — set by server.py at startup
_config: Config = Config()
_indexing: bool = False
_index_progress_subscribers: list[WebSocket] = []
_search_engine = None  # HybridSearchEngine
_pipeline = None  # IndexingPipeline
_embedder = None  # Embedder
_store = None  # MetadataStore
_analytics = None  # AnalyticsStore

# Cached document embeddings for related-doc and collection features
_doc_embeddings: dict = {}
_doc_paths: dict = {}
_doc_filenames: dict = {}
_doc_emb_loaded: bool = False


def _warm_from_store() -> None:
    """Reload search engine from store after index changes."""
    if _store is None or _engine is None:
        return
    import numpy as np
    emb_path = _config.data_dir / "embeddings"
    emb_file = emb_path / "embeddings.npy"
    ids_file = emb_path / "chunk_ids.npy"
    if emb_file.exists() and ids_file.exists():
        embeddings = np.load(str(emb_file)).astype(np.float32)
        chunk_ids = np.load(str(ids_file))
        # Get texts from store
        all_docs = _store.all_documents()
        for doc in all_docs:
            chunks = _store.get_chunks_for_document(doc.id)
            for chunk in chunks:
                text = chunk.text
                cid = str(chunk.id)
                idx = None
                for i, stored_id in enumerate(chunk_ids):
                    if stored_id == chunk.id:
                        idx = i
                        break
                if idx is not None and idx < len(embeddings):
                    _engine.add_documents([(cid, text, embeddings[idx])])


def set_config(config: Config) -> None:
    """Inject configuration at startup."""
    global _config
    _config = config


def get_config() -> Config:
    """Return the current config."""
    return _config


def set_components(search_engine, pipeline, embedder, store) -> None:
    """Inject core components at startup."""
    global _search_engine, _pipeline, _embedder, _store, _analytics
    from desksearch.core.analytics import AnalyticsStore
    _search_engine = search_engine
    _pipeline = pipeline
    _embedder = embedder
    _store = store
    analytics_db = _config.data_dir / "analytics.db"
    _analytics = AnalyticsStore(analytics_db)


def _ensure_doc_embeddings() -> None:
    """Load document-level embeddings (average chunk embeddings) into memory."""
    global _doc_embeddings, _doc_paths, _doc_filenames, _doc_emb_loaded
    if _doc_emb_loaded or _store is None:
        return
    try:
        from desksearch.core.collections import build_doc_embeddings
        emb_path = _config.data_dir / "embeddings"
        _doc_embeddings, _doc_paths, _doc_filenames = build_doc_embeddings(_store, emb_path)
        _doc_emb_loaded = True
        logger.info("Loaded doc embeddings for %d documents", len(_doc_embeddings))
    except Exception as exc:
        logger.warning("Could not load doc embeddings: %s", exc)
        _doc_emb_loaded = True  # don't retry on every request


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@router.get("/search", response_model=RichSearchResponse)
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    type: Optional[str] = Query(None, description="Filter by file type (e.g. pdf)"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    rich: bool = Query(True, description="Include NL answers and related docs"),
) -> RichSearchResponse:
    """Execute a hybrid search query against the index."""
    start = time.perf_counter()

    if _search_engine is None or _embedder is None or _store is None:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return RichSearchResponse(results=[], total=0, query_time_ms=round(elapsed_ms, 2))

    # Embed the query
    loop = asyncio.get_event_loop()
    query_embedding = await loop.run_in_executor(None, _embedder.embed_query, q)

    # Fetch extra candidates to compensate for deduplication and filtering.
    candidate_count = limit * 4
    raw_results = await _search_engine.search(q, query_embedding, top_k=candidate_count)

    # --- Pre-pass: resolve chunk → file metadata for all candidates ---
    chunk_meta: dict[str, tuple] = {}
    for r in raw_results:
        try:
            chunk_id = int(r.doc_id)
        except (ValueError, TypeError):
            continue
        chunk = _store.get_chunk_by_id(chunk_id)
        if chunk is None:
            continue
        doc = _store.get_document_by_id(chunk.doc_id)
        if doc is None:
            continue
        chunk_meta[r.doc_id] = (chunk, doc)

    # --- Compute per-chunk boosts (filename match + recency) ---
    query_tokens = set(re.findall(r"\w+", q.lower()))
    now = time.time()
    boosts: dict[str, float] = {}

    for doc_id, (chunk, doc) in chunk_meta.items():
        multiplier = 1.0

        # Filename boost: reward hits where query terms appear in the filename
        fname_tokens = set(re.findall(r"\w+", doc.filename.lower()))
        overlap = query_tokens & fname_tokens
        if overlap:
            multiplier *= 1.0 + 0.2 * min(len(overlap), 3)

        # Recency boost: small log-decay; ~+8% for files modified today,
        # < 1% after 90 days. Keeps recent files visible without dominating.
        age_days = max(0.0, (now - doc.modified_time) / 86400.0)
        multiplier *= 1.0 + 0.08 * math.exp(-age_days / 30.0)

        if multiplier != 1.0:
            boosts[doc_id] = multiplier

    # Re-search with boosts applied (skips the result cache intentionally)
    if boosts:
        raw_results = await _search_engine.search(
            q, query_embedding, top_k=candidate_count, boosts=boosts
        )

    # --- Deduplication: keep best-scoring chunk per source file ---
    best_per_file: dict[int, tuple] = {}   # file_doc_id → (raw_result, chunk, doc)
    extra_counts: dict[int, int] = {}

    for r in raw_results:
        if r.doc_id not in chunk_meta:
            continue
        chunk, doc = chunk_meta[r.doc_id]
        file_doc_id = doc.id

        if file_doc_id not in best_per_file:
            best_per_file[file_doc_id] = (r, chunk, doc)
            extra_counts[file_doc_id] = 0
        else:
            extra_counts[file_doc_id] += 1

    # Re-sort by boosted score (dict ordering not guaranteed to be stable)
    ranked = sorted(
        best_per_file.values(),
        key=lambda t: t[0].score,
        reverse=True,
    )

    # --- Build final API results ---
    # --- Load doc embeddings for related-doc feature (lazy, once) ---
    if rich and not _doc_emb_loaded:
        loop.run_in_executor(None, _ensure_doc_embeddings)

    # --- NL answer extraction ---
    from desksearch.core.nlsearch import is_question, extract_answer
    nl_answer: Optional[NLAnswer] = None
    query_is_question = is_question(q)

    # Collect chunk texts for answer extraction (before building results list)
    chunk_texts_for_answer: list[tuple[str, float]] = []

    results: list[RichSearchResult] = []
    for r, chunk, doc in ranked:
        file_type = doc.extension.lstrip(".")
        if type and file_type != type:
            continue

        # Use the highlighted snippet for richer display; fall back to raw text
        snippet = r.snippets[0].highlighted if r.snippets else chunk.text[:200]
        modified = datetime.fromtimestamp(doc.modified_time, tz=timezone.utc)

        # Collect for NL answer
        if query_is_question and len(chunk_texts_for_answer) < 5:
            chunk_texts_for_answer.append((chunk.text, r.score))

        # Related docs (using cached doc embeddings)
        related: list[dict] = []
        if rich and _doc_emb_loaded and _doc_embeddings:
            try:
                from desksearch.core.collections import find_related_docs
                related = find_related_docs(
                    doc.id, _doc_embeddings, _doc_paths, _doc_filenames, top_k=3
                )
            except Exception:
                pass

        results.append(RichSearchResult(
            doc_id=r.doc_id,
            path=doc.path,
            filename=doc.filename,
            snippet=snippet,
            score=round(r.score, 4),
            file_type=file_type,
            modified=modified,
            file_size=doc.size,
            other_chunk_count=extra_counts.get(doc.id, 0),
            related_docs=related,
        ))

        if len(results) >= limit:
            break

    # Extract NL answer if applicable
    if query_is_question and chunk_texts_for_answer and rich:
        try:
            answer_text = extract_answer(q, chunk_texts_for_answer)
            if answer_text:
                nl_answer = NLAnswer(answer=answer_text, is_question=True)
        except Exception as exc:
            logger.debug("NL answer extraction failed: %s", exc)

    elapsed_ms = (time.perf_counter() - start) * 1000

    _SLOW_SEARCH_MS = 100
    if elapsed_ms > _SLOW_SEARCH_MS:
        logger.warning(
            "Slow search (%.0fms) for query %r — %d results",
            elapsed_ms, q, len(results),
        )

    # Record search analytics (non-blocking, best-effort)
    if _analytics:
        try:
            _analytics.record_search(q, result_count=len(results))
        except Exception:
            pass

    return RichSearchResponse(
        results=results,
        total=len(results),
        query_time_ms=round(elapsed_ms, 2),
        answer=nl_answer,
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@router.get("/health")
async def health() -> dict:
    """Check the health of all system components.

    Returns a dict with ``status`` ('healthy' | 'degraded' | 'unhealthy')
    and per-component details.  This endpoint never raises — it always
    returns 200 so monitoring systems can read the body for details.
    """
    components: dict[str, dict] = {}
    overall_ok = True
    degraded = False

    # SQLite
    try:
        if _store is not None and _store.ping():
            components["sqlite"] = {
                "status": "ok",
                "doc_count": _store.document_count(),
                "chunk_count": _store.chunk_count(),
            }
        else:
            components["sqlite"] = {"status": "unavailable"}
            overall_ok = False
    except Exception as exc:
        components["sqlite"] = {"status": "error", "error": str(exc)}
        overall_ok = False

    # BM25 (tantivy)
    try:
        if _search_engine is not None and _search_engine.bm25.available:
            components["bm25"] = {
                "status": "ok",
                "doc_count": _search_engine.bm25.doc_count,
            }
        else:
            components["bm25"] = {"status": "unavailable"}
            degraded = True
    except Exception as exc:
        components["bm25"] = {"status": "error", "error": str(exc)}
        degraded = True

    # FAISS (dense)
    try:
        if _search_engine is not None and _search_engine.dense.available:
            components["faiss"] = {
                "status": "ok",
                "vector_count": _search_engine.dense.doc_count,
                "index_type": _search_engine.dense.index_type,
            }
        else:
            components["faiss"] = {"status": "unavailable"}
            degraded = True
    except Exception as exc:
        components["faiss"] = {"status": "error", "error": str(exc)}
        degraded = True

    # Embedder
    try:
        if _embedder is not None:
            components["embedder"] = {
                "status": "ok",
                "loaded": _embedder.is_loaded,
                "backend": _embedder.backend,
                "model": _embedder.model_name,
            }
        else:
            components["embedder"] = {"status": "unavailable"}
            degraded = True
    except Exception as exc:
        components["embedder"] = {"status": "error", "error": str(exc)}
        degraded = True

    # Search mode
    search_mode = "unavailable"
    if _search_engine is not None:
        search_mode = _search_engine.mode

    if not overall_ok:
        status = "unhealthy"
    elif degraded:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "search_mode": search_mode,
        "is_indexing": _indexing,
        "components": components,
    }


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------


@router.post("/index", response_model=IndexStatus)
async def trigger_index(request: IndexRequest) -> IndexStatus:
    """Trigger indexing for the specified paths."""
    global _indexing

    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Indexing pipeline not initialized")

    # Validate paths
    for p in request.paths:
        path = Path(p).expanduser().resolve()
        if not path.exists():
            raise HTTPException(status_code=400, detail=f"Path does not exist: {p}")

    _indexing = True

    async def _run_index() -> None:
        global _indexing
        try:
            import queue
            loop = asyncio.get_event_loop()
            cumulative_done = 0
            cumulative_total = 0

            # First pass: count total files across all folders for accurate progress
            for p in request.paths:
                path = Path(p).expanduser().resolve()
                if path.is_dir():
                    try:
                        count = sum(1 for _ in path.rglob("*") if _.is_file())
                        cumulative_total += count
                    except Exception:
                        cumulative_total += 100  # estimate
                else:
                    cumulative_total += 1

            for p in request.paths:
                path = Path(p).expanduser().resolve()
                if path.is_dir():
                    gen = _pipeline.index_directory(path)
                else:
                    gen = _pipeline.index_file(path)

                progress_queue: queue.Queue = queue.Queue()
                folder_last_current = 0

                def _drain_generator(g, q):
                    """Drain a generator, pushing status to queue."""
                    result = None
                    try:
                        while True:
                            status = next(g)
                            q.put(status)
                    except StopIteration as e:
                        result = e.value
                    q.put(None)  # sentinel
                    return result

                # Run generator in thread, broadcast progress from async context
                task = loop.run_in_executor(None, _drain_generator, gen, progress_queue)

                while True:
                    try:
                        status = await loop.run_in_executor(None, progress_queue.get, True, 0.2)
                    except Exception:
                        if task.done():
                            break
                        continue
                    if status is None:
                        break
                    folder_last_current = status.current or 0
                    current = status.current or 0
                    total = status.total or 0
                    # Use cumulative totals, but don't send 0/0 to frontend
                    broadcast_current = cumulative_done + current
                    broadcast_total = cumulative_total if cumulative_total > 0 else total
                    await _broadcast_progress({
                        "status": status.status.value,
                        "file": status.file,
                        "message": status.message,
                        "current": broadcast_current,
                        "total": broadcast_total,
                    })

                await task
                cumulative_done += folder_last_current
        except Exception:
            logger.exception("Indexing failed")
        finally:
            _indexing = False
            global _doc_emb_loaded
            _doc_emb_loaded = False  # force reload of doc embeddings after re-index
            # Persist FAISS index to disk so it survives restarts
            if _engine:
                try:
                    _engine.save()
                    logger.info("Search index saved to disk")
                except Exception:
                    logger.exception("Failed to save search index")
            await _broadcast_progress({"status": "complete"})

    asyncio.create_task(_run_index())

    doc_count = _store.document_count() if _store else 0
    chunk_count = _store.chunk_count() if _store else 0

    return IndexStatus(
        total_documents=doc_count,
        total_chunks=chunk_count,
        index_size_mb=0.0,
        last_indexed=None,
        is_indexing=True,
    )


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@router.get("/status", response_model=IndexStatus)
async def status() -> IndexStatus:
    """Return current index statistics."""
    doc_count = _store.document_count() if _store else 0
    chunk_count = _store.chunk_count() if _store else 0

    # Compute index size from data_dir
    index_size_mb = 0.0
    try:
        data_dir = _config.data_dir
        if data_dir.exists():
            total_bytes = sum(
                f.stat().st_size for f in data_dir.rglob("*") if f.is_file()
            )
            index_size_mb = round(total_bytes / (1024 * 1024), 2)
    except OSError:
        pass

    return IndexStatus(
        total_documents=doc_count,
        total_chunks=chunk_count,
        index_size_mb=index_size_mb,
        last_indexed=None,
        is_indexing=_indexing,
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@router.get("/settings", response_model=SettingsResponse)
async def get_settings() -> SettingsResponse:
    """Return the current configuration."""
    return SettingsResponse(
        data_dir=str(_config.data_dir),
        index_paths=[str(p) for p in _config.index_paths],
        embedding_model=_config.embedding_model,
        chunk_size=_config.chunk_size,
        chunk_overlap=_config.chunk_overlap,
        host=_config.host,
        port=_config.port,
        file_extensions=_config.file_extensions,
        max_file_size_mb=_config.max_file_size_mb,
        excluded_dirs=_config.excluded_dirs,
        api_key=_config.api_key,
        webhook_urls=_config.webhook_urls,
        slack_webhook_url=_config.slack_webhook_url,
    )


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(update: SettingsUpdateRequest) -> SettingsResponse:
    """Update configuration (partial update — only provided fields change)."""
    global _config
    # Use exclude_unset so explicit None values (clearing a field) pass through
    changes = update.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    config_data = _config.model_dump()
    for key, value in changes.items():
        if key == "index_paths":
            config_data[key] = [Path(p) for p in value]
        elif key in ("api_key", "slack_webhook_url") and value == "":
            config_data[key] = None  # empty string → clear the field
        else:
            config_data[key] = value

    _config = Config(**config_data)
    _config.save()

    # Keep integrations module in sync
    try:
        from desksearch.api.integrations import set_config as _int_set_config
        _int_set_config(_config)
    except Exception:
        pass

    return await get_settings()


@router.post("/v1/api-key/regenerate")
async def regenerate_api_key() -> dict:
    """Generate a new random API key and persist it to config."""
    global _config
    import secrets
    new_key = f"ds-{secrets.token_urlsafe(32)}"
    config_data = _config.model_dump()
    config_data["api_key"] = new_key
    _config = Config(**config_data)
    _config.save()

    try:
        from desksearch.api.integrations import set_config as _int_set_config
        _int_set_config(_config)
    except Exception:
        pass

    return {"api_key": new_key}


@router.delete("/v1/api-key")
async def clear_api_key() -> dict:
    """Remove the API key (disables bearer-token auth on integration endpoints)."""
    global _config
    config_data = _config.model_dump()
    config_data["api_key"] = None
    _config = Config(**config_data)
    _config.save()

    try:
        from desksearch.api.integrations import set_config as _int_set_config
        _int_set_config(_config)
    except Exception:
        pass

    return {"status": "ok", "api_key": None}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=DashboardStats)
async def dashboard() -> DashboardStats:
    """Return dashboard statistics including type breakdown and folder info."""
    if _store is None:
        return DashboardStats()

    docs = _store.all_documents()
    doc_count = len(docs)
    chunk_count = _store.chunk_count()

    # Type breakdown
    type_map: dict[str, int] = {}
    for doc in docs:
        ext = doc.extension.lstrip(".") or "other"
        category = _categorize_extension(ext)
        type_map[category] = type_map.get(category, 0) + 1

    # Index size
    index_size_mb = 0.0
    try:
        data_dir = _config.data_dir
        if data_dir.exists():
            total_bytes = sum(
                f.stat().st_size for f in data_dir.rglob("*") if f.is_file()
            )
            index_size_mb = round(total_bytes / (1024 * 1024), 2)
    except OSError:
        pass

    # Folder info from config index_paths
    folders: list[FolderInfo] = []
    for idx_path in _config.index_paths:
        p = Path(idx_path).expanduser().resolve()
        folder_docs = [d for d in docs if d.path.startswith(str(p))]
        last_idx = max((d.indexed_time for d in folder_docs), default=None)
        folders.append(FolderInfo(
            path=str(p),
            file_count=len(folder_docs),
            last_indexed=datetime.fromtimestamp(last_idx, tz=timezone.utc) if last_idx else None,
            status="watching",
        ))

    return DashboardStats(
        total_documents=doc_count,
        total_chunks=chunk_count,
        index_size_mb=index_size_mb,
        is_indexing=_indexing,
        type_breakdown=type_map,
        watched_folders=folders,
    )


def _categorize_extension(ext: str) -> str:
    """Map file extension to a broad category."""
    pdf = {"pdf"}
    docs = {"docx", "doc", "odt", "rtf"}
    code = {"py", "js", "ts", "java", "c", "cpp", "h", "go", "rs", "rb", "sh",
            "bash", "zsh", "sql", "r", "ipynb", "jsx", "tsx"}
    text = {"txt", "md", "rst", "org", "tex", "csv", "tsv", "log"}
    web = {"html", "htm", "xml", "json", "yaml", "yml", "toml", "css"}
    if ext in pdf:
        return "PDF"
    if ext in docs:
        return "Documents"
    if ext in code:
        return "Code"
    if ext in text:
        return "Text"
    if ext in web:
        return "Web/Config"
    return "Other"


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------


@router.get("/folders", response_model=list[FolderInfo])
async def list_folders() -> list[FolderInfo]:
    """List all watched folders with stats."""
    docs = _store.all_documents() if _store else []
    folders: list[FolderInfo] = []
    for idx_path in _config.index_paths:
        p = Path(idx_path).expanduser().resolve()
        folder_docs = [d for d in docs if d.path.startswith(str(p))]
        last_idx = max((d.indexed_time for d in folder_docs), default=None)
        folders.append(FolderInfo(
            path=str(p),
            file_count=len(folder_docs),
            last_indexed=datetime.fromtimestamp(last_idx, tz=timezone.utc) if last_idx else None,
            status="watching",
        ))
    return folders


@router.post("/folders", response_model=FolderInfo)
async def add_folder(request: FolderAddRequest) -> FolderInfo:
    """Add a new folder to watch."""
    global _config
    p = Path(request.path).expanduser().resolve()
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=400, detail=f"Directory does not exist: {request.path}")

    # Check if already watched
    existing = [Path(ip).expanduser().resolve() for ip in _config.index_paths]
    if p in existing:
        raise HTTPException(status_code=400, detail="Folder already being watched")

    # Update config
    config_data = _config.model_dump()
    config_data["index_paths"] = list(_config.index_paths) + [p]
    _config = Config(**config_data)
    _config.save()

    return FolderInfo(path=str(p), file_count=0, last_indexed=None, status="watching")


@router.delete("/folders/{folder_path:path}")
async def remove_folder(folder_path: str) -> dict[str, str]:
    """Remove a folder from the watch list."""
    global _config
    p = Path(folder_path).expanduser().resolve()
    existing = [Path(ip).expanduser().resolve() for ip in _config.index_paths]
    if p not in existing:
        raise HTTPException(status_code=404, detail="Folder not in watch list")

    new_paths = [ip for ip in _config.index_paths if Path(ip).expanduser().resolve() != p]
    config_data = _config.model_dump()
    config_data["index_paths"] = new_paths
    _config = Config(**config_data)
    _config.save()

    # Also clean up indexed data from this folder
    if _store:
        deleted = _store.delete_documents_by_prefix(str(p))
        if deleted > 0:
            logger.info("Cleaned up %d indexed documents from removed folder: %s", deleted, p)
            # Rebuild search engine index
            if _engine:
                _engine.clear()
                _warm_from_store()

    return {"status": "ok", "removed": str(p)}


@router.delete("/index/clear")
async def clear_index() -> dict[str, str | int]:
    """Clear the entire index — removes all indexed documents and chunks."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Store not initialized")

    docs, chunks = _store.clear_all()

    # Clear search engine
    if _engine:
        _engine.clear()

    # Remove embeddings files
    import shutil
    emb_dir = _config.data_dir / "embeddings"
    if emb_dir.exists():
        shutil.rmtree(emb_dir)
        emb_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Cleared index: %d documents, %d chunks removed", docs, chunks)
    return {"status": "ok", "documents_removed": docs, "chunks_removed": chunks}


@router.delete("/index/folder/{folder_path:path}")
async def clear_folder_index(folder_path: str) -> dict[str, str | int]:
    """Clear indexed data for a specific folder without removing it from the watch list."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Store not initialized")

    p = Path(folder_path).expanduser().resolve()
    deleted = _store.delete_documents_by_prefix(str(p))

    if deleted > 0 and _engine:
        _engine.clear()
        _warm_from_store()

    return {"status": "ok", "folder": str(p), "documents_removed": deleted}


@router.get("/browse-directories")
async def browse_directories(path: str = Query("~", description="Directory path to list")) -> dict:
    """List subdirectories at the given path for folder picker UI."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists() or not p.is_dir():
            raise HTTPException(status_code=400, detail=f"Not a valid directory: {path}")

        dirs = []
        try:
            for entry in sorted(p.iterdir()):
                if entry.is_dir() and not entry.name.startswith('.'):
                    dirs.append({
                        "name": entry.name,
                        "path": str(entry),
                    })
        except PermissionError:
            pass

        parent = str(p.parent) if p.parent != p else None
        return {
            "current": str(p),
            "parent": parent,
            "directories": dirs,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reindex/{folder_path:path}", response_model=IndexStatus)
async def reindex_folder(folder_path: str) -> IndexStatus:
    """Trigger reindex of a specific folder."""
    p = Path(folder_path).expanduser().resolve()
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=400, detail=f"Directory does not exist: {folder_path}")

    # Reuse the index endpoint logic
    request = IndexRequest(paths=[str(p)])
    return await trigger_index(request)


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


@router.get("/files", response_model=FilesResponse)
async def list_files(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str = Query("indexed_time", description="Sort field"),
    sort_dir: str = Query("desc", description="asc or desc"),
    file_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    folder: Optional[str] = Query(None),
) -> FilesResponse:
    """Return paginated list of indexed files."""
    if _store is None:
        return FilesResponse()

    docs = _store.all_documents()

    # Filter
    if file_type:
        docs = [d for d in docs if d.extension.lstrip(".") == file_type]
    if search:
        q = search.lower()
        docs = [d for d in docs if q in d.filename.lower() or q in d.path.lower()]
    if folder:
        folder_resolved = str(Path(folder).expanduser().resolve())
        docs = [d for d in docs if d.path.startswith(folder_resolved)]

    # Sort
    sort_fields = {
        "filename": lambda d: d.filename.lower(),
        "path": lambda d: d.path.lower(),
        "size": lambda d: d.size,
        "modified": lambda d: d.modified_time,
        "indexed_time": lambda d: d.indexed_time,
        "num_chunks": lambda d: d.num_chunks,
        "type": lambda d: d.extension,
    }
    key_fn = sort_fields.get(sort_by, sort_fields["indexed_time"])
    docs.sort(key=key_fn, reverse=(sort_dir == "desc"))

    total = len(docs)
    start = (page - 1) * page_size
    page_docs = docs[start:start + page_size]

    files = [
        FileInfo(
            doc_id=d.id,
            filename=d.filename,
            path=d.path,
            file_type=d.extension.lstrip("."),
            size=d.size,
            modified=datetime.fromtimestamp(d.modified_time, tz=timezone.utc),
            indexed_time=datetime.fromtimestamp(d.indexed_time, tz=timezone.utc),
            num_chunks=d.num_chunks,
        )
        for d in page_docs
    ]

    return FilesResponse(files=files, total=total, page=page, page_size=page_size)


@router.get("/files/{doc_id}/preview", response_model=FilePreview)
async def file_preview(doc_id: int) -> FilePreview:
    """Get a preview of a file's content from its indexed chunks."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Store not initialized")

    doc = _store.get_document_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = _store.get_chunks(doc_id)
    content = "\n".join(c.text for c in chunks)
    # Limit preview to 10000 chars
    if len(content) > 10000:
        content = content[:10000] + "\n\n... (truncated)"

    return FilePreview(
        doc_id=doc.id,
        path=doc.path,
        filename=doc.filename,
        content=content,
        num_chunks=doc.num_chunks,
    )


@router.delete("/files/{doc_id}")
async def remove_file(doc_id: int) -> dict[str, str]:
    """Remove a file from the index."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Store not initialized")

    doc = _store.get_document_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    _store.delete_document(Path(doc.path))
    return {"status": "ok", "removed": doc.path}


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------


@router.get("/activity", response_model=ActivityResponse)
async def activity(limit: int = Query(20, ge=1, le=100)) -> ActivityResponse:
    """Return recent indexing activity (most recently indexed files)."""
    if _store is None:
        return ActivityResponse()

    docs = _store.all_documents()
    docs.sort(key=lambda d: d.indexed_time, reverse=True)
    recent = docs[:limit]

    entries = [
        ActivityEntry(
            filename=d.filename,
            path=d.path,
            indexed_time=datetime.fromtimestamp(d.indexed_time, tz=timezone.utc),
            file_type=d.extension.lstrip("."),
            num_chunks=d.num_chunks,
        )
        for d in recent
    ]

    return ActivityResponse(entries=entries)


# ---------------------------------------------------------------------------
# Autocomplete / Suggestions
# ---------------------------------------------------------------------------


@router.get("/suggest", response_model=SuggestResponse)
async def suggest(
    q: str = Query(..., min_length=1, description="Partial query for autocomplete"),
    limit: int = Query(8, ge=1, le=20),
) -> SuggestResponse:
    """Return autocomplete suggestions for a partial query.

    Combines recent searches + indexed document title matches.
    """
    if not q.strip():
        return SuggestResponse()

    suggestions: list[str] = []
    recent: list[str] = []

    # Recent searches matching the prefix
    if _analytics:
        try:
            recent = _analytics.suggest_from_recent(q, limit=5)
        except Exception:
            pass

    # Document title suggestions (filenames matching prefix)
    title_suggestions: list[str] = []
    if _store:
        try:
            q_lower = q.lower()
            docs = _store.all_documents()
            # Score by prefix match quality
            scored: list[tuple[float, str]] = []
            for doc in docs:
                fname_lower = doc.filename.lower()
                if fname_lower.startswith(q_lower):
                    scored.append((2.0, doc.filename))
                elif q_lower in fname_lower:
                    scored.append((1.0, doc.filename))
            scored.sort(reverse=True)
            seen: set[str] = set()
            for _, fname in scored:
                fname_key = fname.lower()
                if fname_key not in seen:
                    title_suggestions.append(fname)
                    seen.add(fname_key)
                if len(title_suggestions) >= 5:
                    break
        except Exception:
            pass

    # Merge: recent searches first, then title completions
    seen_lower: set[str] = set()
    for s in recent + title_suggestions:
        if s.lower() not in seen_lower:
            suggestions.append(s)
            seen_lower.add(s.lower())
        if len(suggestions) >= limit:
            break

    return SuggestResponse(suggestions=suggestions, recent=recent)


# ---------------------------------------------------------------------------
# Rich Document Preview
# ---------------------------------------------------------------------------


@router.get("/preview/{doc_id}", response_model=RichPreview)
async def rich_preview(doc_id: int) -> RichPreview:
    """Return a rich preview of a document: text excerpt, key phrases, metadata."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Store not initialized")

    doc = _store.get_document_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = _store.get_chunks(doc_id)
    full_text = "\n".join(c.text for c in chunks)

    # Preview: first 500 chars
    preview_text = full_text[:500]
    if len(full_text) > 500:
        # Try to cut at a sentence boundary
        cut = full_text[:500].rfind(". ")
        if cut > 200:
            preview_text = full_text[:cut + 1]
        else:
            preview_text = full_text[:500] + "…"

    # Key phrase extraction
    from desksearch.core.nlsearch import extract_key_phrases
    key_phrases = extract_key_phrases(full_text, max_phrases=8)

    # Word count estimate
    word_count = len(full_text.split())

    modified = datetime.fromtimestamp(doc.modified_time, tz=timezone.utc)

    return RichPreview(
        doc_id=doc.id,
        path=doc.path,
        filename=doc.filename,
        file_type=doc.extension.lstrip("."),
        preview_text=preview_text,
        key_phrases=key_phrases,
        size=doc.size,
        modified=modified,
        num_chunks=doc.num_chunks,
        word_count=word_count,
    )


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


@router.get("/analytics", response_model=AnalyticsSummary)
async def analytics_summary(days: int = Query(30, ge=1, le=365)) -> AnalyticsSummary:
    """Return search analytics: top queries, popular files, search frequency."""
    if _analytics is None:
        return AnalyticsSummary()

    return AnalyticsSummary(
        total_searches=_analytics.total_searches(),
        total_clicks=_analytics.total_clicks(),
        top_searches=_analytics.top_searches(limit=10, days=days),
        top_files=_analytics.top_clicked_files(limit=10, days=days),
        search_over_time=_analytics.search_frequency_over_time(days=days),
    )


@router.post("/analytics/click")
async def track_click(body: dict) -> dict:
    """Track a click on a search result."""
    query = body.get("query", "")
    doc_path = body.get("path", "")
    doc_filename = body.get("filename", "")

    if _analytics and query and doc_path:
        try:
            _analytics.record_click(query, doc_path, doc_filename)
        except Exception:
            pass

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Smart Collections (topic clustering)
# ---------------------------------------------------------------------------


@router.get("/collections", response_model=CollectionsResponse)
async def get_collections(
    n_topics: Optional[int] = Query(None, ge=2, le=20, description="Number of topics (auto if not set)"),
) -> CollectionsResponse:
    """Auto-cluster documents into topic collections using k-means on embeddings."""
    if _store is None:
        return CollectionsResponse()

    # Load doc embeddings
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _ensure_doc_embeddings)

    if not _doc_embeddings:
        return CollectionsResponse()

    try:
        from desksearch.core.collections import cluster_documents
        topics = await loop.run_in_executor(
            None,
            cluster_documents,
            _doc_embeddings, _doc_paths, _doc_filenames, n_topics,
        )
    except Exception as exc:
        logger.error("Clustering failed: %s", exc)
        return CollectionsResponse()

    topic_infos = [
        TopicInfo(
            id=t.id,
            label=t.label,
            doc_count=len(t.doc_ids),
            doc_ids=t.doc_ids,
            doc_filenames=t.doc_filenames,
            doc_paths=t.doc_paths,
        )
        for t in topics
    ]

    total = sum(len(t.doc_ids) for t in topics)
    return CollectionsResponse(topics=topic_infos, total_docs_clustered=total)


# ---------------------------------------------------------------------------
# Duplicate File Detection
# ---------------------------------------------------------------------------


@router.get("/duplicates", response_model=DuplicatesResponse)
async def find_duplicates_endpoint(
    threshold: float = Query(0.92, ge=0.5, le=0.9999, description="Similarity threshold"),
) -> DuplicatesResponse:
    """Find documents with very similar content (potential duplicates)."""
    if _store is None:
        return DuplicatesResponse()

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _ensure_doc_embeddings)

    if not _doc_embeddings:
        return DuplicatesResponse()

    try:
        from desksearch.core.collections import find_duplicates
        pairs_raw = await loop.run_in_executor(
            None,
            find_duplicates,
            _doc_embeddings, _doc_paths, _doc_filenames, threshold,
        )
    except Exception as exc:
        logger.error("Duplicate detection failed: %s", exc)
        return DuplicatesResponse()

    pairs = [DuplicatePair(**p) for p in pairs_raw]
    return DuplicatesResponse(pairs=pairs, total=len(pairs))


# ---------------------------------------------------------------------------
# Related Documents
# ---------------------------------------------------------------------------


@router.get("/related/{doc_id}")
async def get_related_docs(
    doc_id: int,
    top_k: int = Query(5, ge=1, le=20),
) -> dict:
    """Find documents semantically similar to a given document."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Store not initialized")

    doc = _store.get_document_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _ensure_doc_embeddings)

    if not _doc_embeddings:
        return {"related": [], "doc_id": doc_id}

    try:
        from desksearch.core.collections import find_related_docs
        related = find_related_docs(doc_id, _doc_embeddings, _doc_paths, _doc_filenames, top_k=top_k)
    except Exception as exc:
        logger.error("Related docs failed: %s", exc)
        related = []

    return {"related": related, "doc_id": doc_id, "filename": doc.filename}


# ---------------------------------------------------------------------------
# Open file
# ---------------------------------------------------------------------------


@router.get("/open/{doc_id:path}")
async def open_file(doc_id: str) -> dict[str, str]:
    """Open a file in the system default application."""
    path = Path(doc_id).expanduser().resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {doc_id}")

    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", str(path)])
        elif system == "Linux":
            subprocess.Popen(["xdg-open", str(path)])
        elif system == "Windows":
            subprocess.Popen(["cmd", "/c", "start", "", str(path)])
        else:
            raise HTTPException(
                status_code=500, detail=f"Unsupported platform: {system}"
            )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500, detail=f"Could not open file: {exc}"
        ) from exc

    return {"status": "ok", "path": str(path)}


# ---------------------------------------------------------------------------
# WebSocket — live indexing progress
# ---------------------------------------------------------------------------

ws_router = APIRouter()


@ws_router.websocket("/ws/index-progress")
async def index_progress(websocket: WebSocket) -> None:
    """WebSocket endpoint that streams indexing progress events."""
    await websocket.accept()
    _index_progress_subscribers.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _index_progress_subscribers:
            _index_progress_subscribers.remove(websocket)


async def _broadcast_progress(data: dict) -> None:
    """Send a progress event to all connected WebSocket clients."""
    dead: list[WebSocket] = []
    for ws in _index_progress_subscribers:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _index_progress_subscribers.remove(ws)

    # Fire webhook notifications when indexing finishes
    if data.get("status") == "complete":
        try:
            from desksearch.api.integrations import notify_webhooks
            doc_count = _store.document_count() if _store else 0
            asyncio.create_task(
                notify_webhooks(
                    "indexing_complete",
                    {"total_documents": doc_count},
                )
            )
        except Exception:
            pass  # Webhooks are optional — never block core functionality


# ---------------------------------------------------------------------------
# Memory / resource monitoring
# ---------------------------------------------------------------------------


@router.get("/memory")
async def memory_info() -> dict:
    """Return process memory and resource usage information."""
    import os
    import resource
    import sys
    import threading

    # Process RSS
    try:
        if sys.platform == "darwin":
            import subprocess
            out = subprocess.check_output(
                ["ps", "-o", "rss=", "-p", str(os.getpid())],
                text=True,
            ).strip()
            rss_mb = int(out) / 1024
        else:
            with open(f"/proc/{os.getpid()}/status") as f:
                rss_mb = 0.0
                for line in f:
                    if line.startswith("VmRSS:"):
                        rss_mb = int(line.split()[1]) / 1024
                        break
    except Exception:
        ru = resource.getrusage(resource.RUSAGE_SELF)
        rss_mb = ru.ru_maxrss / (1024 * 1024) if sys.platform == "darwin" else ru.ru_maxrss / 1024

    # Model status
    model_loaded = False
    model_name = None
    if _embedder is not None:
        model_loaded = _embedder.is_loaded
        model_name = _embedder.model_name

    # Index sizes
    dense_count = 0
    dense_index_type = "N/A"
    bm25_count = 0
    if _search_engine is not None:
        try:
            dense_count = _search_engine.dense.doc_count
            dense_index_type = _search_engine.dense.index_type
        except Exception:
            pass
        try:
            bm25_count = _search_engine.bm25.doc_count
        except Exception:
            pass

    doc_count = _store.document_count() if _store else 0
    chunk_count = _store.chunk_count() if _store else 0

    return {
        "process": {
            "pid": os.getpid(),
            "rss_mb": round(rss_mb, 1),
            "active_threads": threading.active_count(),
            "thread_names": [t.name for t in threading.enumerate()],
        },
        "model": {
            "loaded": model_loaded,
            "name": model_name,
        },
        "indexes": {
            "dense_vectors": dense_count,
            "dense_type": dense_index_type,
            "bm25_documents": bm25_count,
            "store_documents": doc_count,
            "store_chunks": chunk_count,
        },
    }


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------


@router.get("/onboarding/status")
async def onboarding_status() -> dict:
    """Check if first-run setup is needed."""
    from desksearch.onboarding import is_first_run

    has_folders = bool(_config.index_paths)
    doc_count = _store.document_count() if _store else 0
    return {
        "is_first_run": is_first_run(),
        "needs_setup": is_first_run() or (not has_folders and doc_count == 0),
        "has_indexed_documents": doc_count > 0,
    }


@router.get("/onboarding/detect-folders")
async def onboarding_detect_folders() -> dict:
    """Auto-detect common folders for indexing."""
    from desksearch.onboarding import detect_folders as _detect

    detected = _detect()
    folders = []
    for category, paths in detected.items():
        for p in paths:
            folders.append({
                "path": str(p),
                "name": p.name,
                "category": category,
            })
    return {"folders": folders}


@router.post("/onboarding/setup")
async def onboarding_setup(request: dict) -> dict:
    """Save selected folders and optionally start indexing."""
    global _config, _indexing

    selected_paths = request.get("paths", [])
    if not selected_paths:
        raise HTTPException(status_code=400, detail="No paths provided")

    valid_paths = []
    for p in selected_paths:
        path = Path(p).expanduser().resolve()
        if path.is_dir():
            valid_paths.append(str(path))

    if not valid_paths:
        raise HTTPException(status_code=400, detail="No valid directories found")

    # Update config
    config_data = _config.model_dump()
    config_data["index_paths"] = [Path(p) for p in valid_paths]
    _config = Config(**config_data)
    _config.save()

    # Start indexing if requested
    start_indexing = request.get("start_indexing", True)
    if start_indexing and _pipeline is not None:
        _indexing = True

        async def _run_onboarding_index() -> None:
            global _indexing
            try:
                loop = asyncio.get_event_loop()
                for p in valid_paths:
                    path = Path(p)
                    if not path.is_dir():
                        continue
                    gen = _pipeline.index_directory(path)

                    def _drain(g):
                        try:
                            while True:
                                next(g)
                        except StopIteration:
                            pass

                    await loop.run_in_executor(None, _drain, gen)
            except Exception:
                logger.exception("Onboarding indexing failed")
            finally:
                _indexing = False
                await _broadcast_progress({"status": "complete"})

        asyncio.create_task(_run_onboarding_index())

    return {
        "status": "ok",
        "paths": valid_paths,
        "indexing_started": start_indexing,
    }
