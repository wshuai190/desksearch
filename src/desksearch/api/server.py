"""FastAPI application factory for DeskSearch."""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from desksearch.api.routes import router, ws_router, set_config, set_components
from desksearch.config import Config
from desksearch.core.search import HybridSearchEngine
from desksearch.indexer.embedder import Embedder
from desksearch.indexer.pipeline import IndexingPipeline
from desksearch.indexer.store import MetadataStore
from desksearch.utils.memory import log_memory, log_memory_delta

logger = logging.getLogger(__name__)

# Look for UI files: first in package (pip install), then in source tree (dev)
_pkg_ui = Path(__file__).resolve().parent.parent / "ui_dist"
_src_ui = Path(__file__).resolve().parent.parent.parent / "ui" / "dist"
UI_DIST_DIR = _pkg_ui if _pkg_ui.exists() else _src_ui


def create_app(
    config: Config | None = None,
    *,
    store: MetadataStore | None = None,
    embedder: Embedder | None = None,
    engine: HybridSearchEngine | None = None,
    pipeline: IndexingPipeline | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    When called without pre-built components (standalone mode), initializes
    everything from scratch.  When called with pre-built components (daemon
    mode), reuses them so there is a single shared embedder / engine / store.
    """
    config = config or Config.load()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    set_config(config)

    # Track whether components were pre-built (daemon mode) or created here
    is_standalone = embedder is None

    # Initialize core components — single instances shared across the app
    store = store or MetadataStore(config.data_dir / "metadata.db")
    embedder = embedder or Embedder(config.embedding_model)
    engine = engine or HybridSearchEngine(config)
    pipeline = pipeline or IndexingPipeline(
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

    log_memory_delta(mem_before, "startup-after-warm")

    set_components(engine, pipeline, embedder, store)

    app = FastAPI(
        title="DeskSearch",
        description="Private semantic search engine for your local files",
        version="0.1.0",
    )

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

    # API + WebSocket routes
    app.include_router(router)
    app.include_router(ws_router)

    # Auto-index on startup if folders are configured but nothing is indexed
    @app.on_event("startup")
    async def _auto_index_if_empty():
        import asyncio
        if store and store.document_count() == 0 and config.index_paths:
            import logging
            logger = logging.getLogger("desksearch")
            logger.info("No indexed files found. Auto-indexing configured folders...")
            # Trigger indexing via the API endpoint internally
            from desksearch.api.schemas import IndexRequest
            req = IndexRequest(paths=[str(p) for p in config.index_paths])
            try:
                await trigger_index(req)
            except Exception as e:
                logger.warning(f"Auto-index failed: {e}")

    # Import trigger_index for auto-index
    from desksearch.api.routes import trigger_index

    # Serve built React UI if available
    if UI_DIST_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(UI_DIST_DIR), html=True), name="ui")

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
        "%d docs in BM25 | %d vectors in FAISS",
        doc_count, chunk_count, bm25_docs, faiss_vecs,
    )
