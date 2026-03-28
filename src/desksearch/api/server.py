"""FastAPI application factory for DeskSearch."""
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from desksearch.api.routes import router, ws_router, set_config, set_components, set_watcher
from desksearch.api.integrations import (
    integrations_router,
    set_config as integrations_set_config,
    set_components as integrations_set_components,
)
from desksearch.api.connectors import connector_router, set_connector_components
from desksearch.config import Config
from desksearch.utils.memory import log_memory, log_memory_delta

# Lazy imports for heavy modules — defer loading of torch/transformers/faiss/onnxruntime
# until actually needed (when create_app instantiates components).


def _get_connector_registry():
    from desksearch.connectors import ConnectorRegistry
    return ConnectorRegistry()


def _get_search_engine(config, dimension):
    from desksearch.core.search import HybridSearchEngine
    return HybridSearchEngine(config, dimension=dimension)


def _get_embedder(model_name, embedding_dim, embedding_layers):
    from desksearch.indexer.embedder import Embedder
    return Embedder(model_name, embedding_dim=embedding_dim, embedding_layers=embedding_layers)


def _get_pipeline(config, search_engine, embedder, store):
    from desksearch.indexer.pipeline import IndexingPipeline
    return IndexingPipeline(config, search_engine=search_engine, embedder=embedder, store=store)


def _get_store(db_path):
    from desksearch.indexer.store import MetadataStore
    return MetadataStore(db_path)


def _get_file_watcher(config, on_created, on_modified, on_deleted):
    from desksearch.indexer.watcher import FileWatcher
    return FileWatcher(config, on_created=on_created, on_modified=on_modified, on_deleted=on_deleted)

logger = logging.getLogger(__name__)

# Requests that take longer than this are logged as warnings.
_SLOW_REQUEST_MS = 2000

# Look for UI files: first in package (pip install), then in source tree (dev)
_pkg_ui = Path(__file__).resolve().parent.parent / "ui_dist"
_src_ui = Path(__file__).resolve().parent.parent.parent / "ui" / "dist"
UI_DIST_DIR = _pkg_ui if _pkg_ui.exists() else _src_ui


def create_app(
    config: Config | None = None,
    *,
    store=None,
    embedder=None,
    engine=None,
    pipeline=None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    When called without pre-built components (standalone mode), initializes
    everything from scratch.  When called with pre-built components (daemon
    mode), reuses them so there is a single shared embedder / engine / store.
    """
    t_startup = time.perf_counter()

    config = config or Config.load()
    config.data_dir.mkdir(parents=True, exist_ok=True)

    # --- Config validation ---
    issues = config.validate()
    for issue in issues:
        logger.warning("Config issue: %s", issue)

    set_config(config)
    integrations_set_config(config)

    # Track whether components were pre-built (daemon mode) or created here
    is_standalone = embedder is None

    # Initialize core components — single instances shared across the app.
    # Heavy modules (torch, transformers, faiss, onnxruntime) are imported
    # lazily inside factory functions to speed up module import time.
    store = store or _get_store(config.data_dir / "metadata.db")
    # Resolve Starbucks tier (updates config.embedding_dim and embedding_layers)
    config.resolve_starbucks_tier()
    embedder = embedder or _get_embedder(
        config.embedding_model,
        embedding_dim=config.embedding_dim,
        embedding_layers=config.embedding_layers,
    )
    engine = engine or _get_search_engine(
        config, dimension=config.embedding_dim,
    )
    pipeline = pipeline or _get_pipeline(
        config, search_engine=engine, embedder=embedder, store=store,
    )

    # Lazy loading: the embedding model loads on first use (search or index).
    # Eagerly warming the model here keeps 100-200 MB loaded even when idle,
    # which conflicts with the <200 MB idle-memory budget.

    # Log baseline memory before loading existing index data.
    mem_before = log_memory("startup-before-warm")

    # Load previously indexed data into the live search engine.
    # BM25 (tantivy) and FAISS both reload from disk automatically in their
    # constructors, so this call only needs to do lightweight bookkeeping.
    if is_standalone:
        _warm_search_engine(engine, store, config)
        # VACUUM SQLite in the background if fragmented — safe at startup
        # because no writes are in-flight yet.
        try:
            store.vacuum_if_fragmented()
        except Exception as _e:
            logger.debug("VACUUM skipped: %s", _e)

    log_memory_delta(mem_before, "startup-after-warm")

    set_components(engine, pipeline, embedder, store)
    integrations_set_components(engine, pipeline, embedder, store)

    # --- File watcher for incremental indexing ---
    def _on_file_created(path):
        logger.info("Watcher: indexing new file %s", path)
        try:
            pipeline.index_single_file(path)
        except Exception:
            logger.exception("Watcher: failed to index %s", path)

    def _on_file_modified(path):
        logger.info("Watcher: re-indexing modified file %s", path)
        try:
            pipeline.remove_file(path)
            pipeline.index_single_file(path)
        except Exception:
            logger.exception("Watcher: failed to re-index %s", path)

    def _on_file_deleted(path):
        logger.info("Watcher: removing deleted file %s", path)
        try:
            pipeline.remove_file(path)
        except Exception:
            logger.exception("Watcher: failed to remove %s", path)

    watcher = _get_file_watcher(
        config,
        on_created=_on_file_created,
        on_modified=_on_file_modified,
        on_deleted=_on_file_deleted,
    )
    set_watcher(watcher)

    # --- Lifespan: replaces deprecated @app.on_event("startup"/"shutdown") ---
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: start file watcher and auto-index if empty
        try:
            watcher.start()
            logger.info("File watcher started for %d paths", len(config.index_paths))
        except Exception:
            logger.exception("Failed to start file watcher")

        # Auto-index on startup if folders are configured but nothing indexed
        if store and store.document_count() == 0 and config.index_paths:
            logger.info("No indexed files found. Auto-indexing configured folders...")
            from desksearch.api.schemas import IndexRequest
            req = IndexRequest(paths=[str(p) for p in config.index_paths])
            try:
                await trigger_index(req)
            except Exception as e:
                logger.warning("Auto-index failed: %s", e)

        yield  # App is running

        # Shutdown: stop file watcher
        try:
            watcher.stop()
            logger.info("File watcher stopped")
        except Exception:
            logger.exception("Failed to stop file watcher")

    # Import trigger_index for auto-index in lifespan
    from desksearch.api.routes import trigger_index

    # Note: ORJSONResponse is deprecated in newer FastAPI — it now serializes
    # data directly to JSON bytes via Pydantic when a return type or response
    # model is set, which is already fast. No custom response class needed.
    app = FastAPI(
        title="DeskSearch",
        description="Private semantic search engine for your local files",
        version="0.1.0",
        lifespan=lifespan,
    )

    # --- Request timing middleware ---
    @app.middleware("http")
    async def timing_middleware(request: Request, call_next) -> Response:
        """Record per-request latency and warn on slow requests."""
        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"
        if elapsed_ms > _SLOW_REQUEST_MS:
            logger.warning(
                "Slow request: %s %s — %.0fms",
                request.method,
                request.url.path,
                elapsed_ms,
            )
        else:
            logger.debug(
                "%s %s — %.1fms",
                request.method,
                request.url.path,
                elapsed_ms,
            )
        return response

    # CORS — allow the dev Vite server and the bundled UI
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite dev server
            f"http://localhost:{config.port}",
            f"http://127.0.0.1:{config.port}",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Connector registry (v2 connector system)
    connector_registry = _get_connector_registry()
    connector_registry.discover()
    set_connector_components(connector_registry, pipeline)

    # API + WebSocket routes
    app.include_router(router)
    app.include_router(ws_router)
    app.include_router(integrations_router)
    app.include_router(connector_router)

    # Serve built React UI if available
    if UI_DIST_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(UI_DIST_DIR), html=True), name="ui")

    startup_s = time.perf_counter() - t_startup
    logger.info("DeskSearch ready in %.1fs", startup_s)

    return app


def _warm_search_engine(engine, store, config) -> None:
    """Log index state on startup — no heavy lifting needed.

    BM25 (tantivy) and FAISS both persist to disk and reload their data
    automatically in their constructors.  The old implementation re-loaded
    all embeddings from ``embeddings.npy`` and re-added every chunk to both
    indexes, which was entirely redundant and wasted 50-200 MB of RAM.

    We now just log counts so operators can confirm the index is healthy.
    The ``_doc_texts`` LRU cache in the search engine fills on demand as
    searches run, with BM25 as a fallback for cache misses.
    """
    doc_count = store.document_count()
    chunk_count = store.chunk_count()
    bm25_docs = engine.bm25.doc_count
    faiss_vecs = engine.dense.doc_count
    logger.info(
        "Index ready: %d documents, %d chunks in SQLite | "
        "%d docs in BM25 | %d vectors in FAISS | mode=%s",
        doc_count, chunk_count, bm25_docs, faiss_vecs, engine.mode,
    )
