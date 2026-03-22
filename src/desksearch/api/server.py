"""FastAPI application factory for DeskSearch."""
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

UI_DIST_DIR = Path(__file__).resolve().parent.parent.parent / "ui" / "dist"


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

    # In standalone mode, eagerly load the model so first search is fast.
    # In daemon mode, the daemon controls model lifecycle (lazy load).
    if is_standalone:
        embedder.warmup()

    # Load existing chunks into the search engine from the store.
    # Skip in daemon mode — the daemon already warms the engine in _init_pipeline.
    if is_standalone:
        _warm_search_engine(engine, store, embedder, config)

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

    # Serve built React UI if available
    if UI_DIST_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(UI_DIST_DIR), html=True), name="ui")

    return app


def _warm_search_engine(engine, store, embedder, config) -> None:
    """Load previously indexed chunks into the search engine on startup.

    Reads chunk texts from SQLite and their embeddings from the saved .npy
    files. If the .npy files are missing (first run or cleared), this is a
    no-op and the engine starts empty.
    """
    import logging
    import numpy as np

    logger = logging.getLogger(__name__)

    embeddings_dir = config.data_dir / "embeddings"
    emb_path = embeddings_dir / "embeddings.npy"
    ids_path = embeddings_dir / "chunk_ids.npy"

    if not emb_path.exists() or not ids_path.exists():
        return

    try:
        embeddings = np.load(str(emb_path))
        chunk_ids = np.load(str(ids_path))
    except Exception:
        logger.warning("Failed to load saved embeddings, starting with empty index")
        return

    # Batch-load chunks to avoid per-document tantivy writer lock churn
    batch: list[tuple[str, str, np.ndarray]] = []
    WARM_BATCH_SIZE = 256

    for i, chunk_id in enumerate(chunk_ids):
        chunk = store.get_chunk_by_id(int(chunk_id))
        if chunk is None:
            continue
        batch.append((str(int(chunk_id)), chunk.text, embeddings[i]))

        if len(batch) >= WARM_BATCH_SIZE:
            engine.add_documents(batch)
            batch.clear()

    if batch:
        engine.add_documents(batch)

    if len(chunk_ids):
        logger.info("Loaded %d chunks into search engine", len(chunk_ids))
