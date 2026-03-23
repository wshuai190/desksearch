"""Background daemon service for DeskSearch.

Manages the FastAPI server, file watcher, and indexing pipeline as a
long-running background process with PID file management, logging, and
resource limits to keep the daemon lightweight.
"""
import gc
import json
import logging
import logging.handlers
import os
import resource
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import uvicorn

from desksearch.config import Config

logger = logging.getLogger(__name__)

PID_FILE = Path.home() / ".desksearch" / "desksearch.pid"
LOG_FILE = Path.home() / ".desksearch" / "desksearch.log"
HEALTH_FILE = Path.home() / ".desksearch" / "health.json"

# Resource defaults
DEFAULT_MAX_MEMORY_MB = 200
DEFAULT_NICE_LEVEL = 10
MAX_CONCURRENT_INDEX = 2
MEMORY_CHECK_INTERVAL = 30  # seconds


def _setup_logging() -> None:
    """Configure file-based logging for the daemon."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=3,
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # Also capture uvicorn logs
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).addHandler(handler)


def _get_rss_mb() -> float:
    """Return current process RSS in megabytes."""
    try:
        ru = resource.getrusage(resource.RUSAGE_SELF)
        # On macOS ru_maxrss is in bytes, on Linux it's in KB
        if sys.platform == "darwin":
            return ru.ru_maxrss / (1024 * 1024)
        return ru.ru_maxrss / 1024
    except Exception:
        return 0.0


def _get_rss_mb_precise() -> float:
    """Return current RSS from /proc or ps (more accurate than ru_maxrss)."""
    try:
        if sys.platform == "darwin":
            import subprocess
            out = subprocess.check_output(
                ["ps", "-o", "rss=", "-p", str(os.getpid())],
                text=True,
            ).strip()
            return int(out) / 1024  # ps reports in KB on macOS
        else:
            # Linux: read from /proc
            with open(f"/proc/{os.getpid()}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) / 1024  # KB -> MB
    except Exception:
        pass
    return _get_rss_mb()


def _is_memory_pressure_high() -> bool:
    """Check if the system is under memory pressure."""
    try:
        if sys.platform == "darwin":
            import subprocess
            out = subprocess.check_output(
                ["sysctl", "-n", "kern.memorystatus_level"],
                text=True, timeout=5,
            ).strip()
            # memorystatus_level is a percentage of free memory; low = pressure
            level = int(out)
            return level < 15  # less than 15% free
        else:
            # Linux: check /proc/meminfo
            with open("/proc/meminfo") as f:
                info = {}
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        info[parts[0].rstrip(":")] = int(parts[1])
            total = info.get("MemTotal", 1)
            available = info.get("MemAvailable", total)
            return (available / total) < 0.15
    except Exception:
        return False


class BackgroundService:
    """Manages DeskSearch as a background daemon process."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config.load()
        self._server: Optional[uvicorn.Server] = None
        self._watcher = None
        self._pipeline = None
        self._engine = None
        self._store = None
        self._embedder = None
        self._shutdown_event = threading.Event()
        self._start_time: Optional[datetime] = None
        self._indexing_paused = False
        self._reindex_queue: list[tuple[str, Path]] = []
        self._queue_lock = threading.Lock()
        self._throttle_delay = 0.5  # seconds between indexing operations
        self._index_semaphore = threading.Semaphore(MAX_CONCURRENT_INDEX)

        # Resource limits
        self.max_memory_mb = getattr(config, 'max_memory_mb', None) or DEFAULT_MAX_MEMORY_MB

    # ------------------------------------------------------------------
    # Resource management
    # ------------------------------------------------------------------

    def _apply_resource_limits(self) -> None:
        """Apply process-level resource limits."""
        # Set nice level to lower priority
        try:
            os.nice(DEFAULT_NICE_LEVEL)
            logger.info("Set process nice level to %d", DEFAULT_NICE_LEVEL)
        except OSError as e:
            logger.warning("Could not set nice level: %s", e)

        # On macOS/Linux: set soft memory limit via setrlimit
        try:
            soft_bytes = self.max_memory_mb * 1024 * 1024
            # Set the address space limit (soft only, leave hard unlimited)
            _soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            resource.setrlimit(resource.RLIMIT_AS, (soft_bytes, hard))
            logger.info("Set RLIMIT_AS soft limit to %dMB", self.max_memory_mb)
        except (ValueError, OSError) as e:
            logger.warning("Could not set RLIMIT_AS: %s", e)

    def _monitor_resources(self) -> None:
        """Periodically check memory usage and take action if needed."""
        while not self._shutdown_event.is_set():
            self._shutdown_event.wait(timeout=MEMORY_CHECK_INTERVAL)
            if self._shutdown_event.is_set():
                break

            rss_mb = _get_rss_mb_precise()
            logger.info(
                "Memory: RSS=%.1fMB (limit=%dMB), model_loaded=%s",
                rss_mb, self.max_memory_mb,
                self._embedder.is_loaded if self._embedder else "N/A",
            )

            # If over memory limit, unload the embedding model
            if rss_mb > self.max_memory_mb and self._embedder and self._embedder.is_loaded:
                logger.warning(
                    "RSS %.1fMB exceeds limit %dMB — unloading embedding model",
                    rss_mb, self.max_memory_mb,
                )
                self._embedder.cooldown()
                gc.collect()

            # If system memory pressure is high, pause indexing
            if _is_memory_pressure_high():
                if not self._indexing_paused:
                    logger.warning("High system memory pressure — pausing indexing")
                    self._indexing_paused = True
            else:
                if self._indexing_paused:
                    logger.info("Memory pressure relieved — resuming indexing")
                    self._indexing_paused = False

    # ------------------------------------------------------------------
    # PID file management
    # ------------------------------------------------------------------

    @staticmethod
    def read_pid() -> Optional[int]:
        """Read PID from the pid file, return None if not found or stale."""
        if not PID_FILE.exists():
            return None
        try:
            pid = int(PID_FILE.read_text().strip())
            # Check if process is alive
            os.kill(pid, 0)
            return pid
        except (ValueError, OSError):
            # Stale PID file
            PID_FILE.unlink(missing_ok=True)
            return None

    def _write_pid(self) -> None:
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))

    def _remove_pid(self) -> None:
        PID_FILE.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Health tracking
    # ------------------------------------------------------------------

    def _write_health(self) -> None:
        """Write health status to a JSON file for status checks."""
        doc_count = 0
        chunk_count = 0
        if self._store:
            try:
                doc_count = self._store.document_count()
                chunk_count = self._store.chunk_count()
            except Exception:
                pass

        data = {
            "status": "running",
            "pid": os.getpid(),
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "paused": self._indexing_paused,
            "documents": doc_count,
            "chunks": chunk_count,
            "host": self.config.host,
            "port": self.config.port,
            "memory_rss_mb": round(_get_rss_mb_precise(), 1),
            "model_loaded": self._embedder.is_loaded if self._embedder else False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        HEALTH_FILE.write_text(json.dumps(data, indent=2))

    # ------------------------------------------------------------------
    # File watcher callbacks
    # ------------------------------------------------------------------

    def _on_file_created(self, path: Path) -> None:
        if self._indexing_paused:
            return
        with self._queue_lock:
            self._reindex_queue.append(("index", path))

    def _on_file_modified(self, path: Path) -> None:
        if self._indexing_paused:
            return
        with self._queue_lock:
            self._reindex_queue.append(("index", path))

    def _on_file_deleted(self, path: Path) -> None:
        with self._queue_lock:
            self._reindex_queue.append(("delete", path))

    def _process_queue(self) -> None:
        """Background thread that drains the reindex queue with throttling.

        Limits concurrent file indexing to MAX_CONCURRENT_INDEX.
        """
        while not self._shutdown_event.is_set():
            items = []
            with self._queue_lock:
                items = list(self._reindex_queue)
                self._reindex_queue.clear()

            for action, path in items:
                if self._shutdown_event.is_set():
                    break
                # Skip indexing if paused (but still process deletes)
                if self._indexing_paused and action == "index":
                    with self._queue_lock:
                        self._reindex_queue.append((action, path))
                    continue

                # Acquire semaphore to limit concurrent indexing
                self._index_semaphore.acquire()
                try:
                    self._process_single(action, path)
                finally:
                    self._index_semaphore.release()

                time.sleep(self._throttle_delay)

            # Update health file periodically
            try:
                self._write_health()
            except Exception:
                pass

            self._shutdown_event.wait(timeout=1.0)

    def _process_single(self, action: str, path: Path) -> None:
        """Process a single queue item."""
        t0 = time.perf_counter()
        try:
            if action == "delete":
                if self._pipeline:
                    doc = self._store.get_document(path) if self._store else None
                    if doc and self._store:
                        if self._engine:
                            chunks = self._store.get_chunks(doc.id)
                            for chunk in chunks:
                                self._engine.delete_document(str(chunk.id))
                        self._store.delete_document(path)
                    elapsed = (time.perf_counter() - t0) * 1000
                    logger.info("Removed from index: %s (%.0fms)", path, elapsed)
            elif action == "index" and self._pipeline:
                gen = self._pipeline.index_file(path)
                try:
                    while True:
                        next(gen)
                except StopIteration:
                    pass
                elapsed = (time.perf_counter() - t0) * 1000
                logger.info("Indexed: %s (%.0fms)", path, elapsed)
        except Exception:
            logger.exception("Error processing %s for %s", action, path)

    # ------------------------------------------------------------------
    # Server management
    # ------------------------------------------------------------------

    def _start_server(self) -> None:
        """Start the FastAPI server in a background thread.

        Passes the daemon's shared components so the server reuses them
        instead of creating a second set.
        """
        from desksearch.api.server import create_app

        app = create_app(
            self.config,
            store=self._store,
            embedder=self._embedder,
            engine=self._engine,
            pipeline=self._pipeline,
        )

        # Add daemon-specific health endpoint
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse

        @app.get("/api/health")
        async def health_check():
            doc_count = 0
            chunk_count = 0
            if self._store:
                try:
                    doc_count = self._store.document_count()
                    chunk_count = self._store.chunk_count()
                except Exception:
                    pass
            return JSONResponse({
                "status": "healthy",
                "pid": os.getpid(),
                "uptime_seconds": (
                    (datetime.now(timezone.utc) - self._start_time).total_seconds()
                    if self._start_time else 0
                ),
                "paused": self._indexing_paused,
                "documents": doc_count,
                "chunks": chunk_count,
                "memory_rss_mb": round(_get_rss_mb_precise(), 1),
                "model_loaded": self._embedder.is_loaded if self._embedder else False,
            })

        config = uvicorn.Config(
            app,
            host=self.config.host,
            port=self.config.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        thread = threading.Thread(target=self._server.run, daemon=True, name="uvicorn")
        thread.start()
        logger.info("API server started on %s:%d", self.config.host, self.config.port)

    def _start_watcher(self) -> None:
        """Start the filesystem watcher."""
        from desksearch.indexer.watcher import FileWatcher

        self._watcher = FileWatcher(
            self.config,
            on_created=self._on_file_created,
            on_modified=self._on_file_modified,
            on_deleted=self._on_file_deleted,
        )
        self._watcher.start()

    def _init_pipeline(self) -> None:
        """Initialize the indexing pipeline and search engine.

        Creates a single set of shared components (store, embedder, engine,
        pipeline) that are reused by both the API server and the daemon's
        background queue processor.

        NOTE: The embedding model is NOT eagerly loaded here. It will be
        loaded lazily on the first search or index operation to keep
        daemon startup lightweight.
        """
        from desksearch.core.search import HybridSearchEngine
        from desksearch.indexer.embedder import Embedder
        from desksearch.indexer.pipeline import IndexingPipeline
        from desksearch.indexer.store import MetadataStore

        self._store = MetadataStore(self.config.data_dir / "metadata.db")
        self.config.resolve_starbucks_tier()
        self._embedder = Embedder(
            self.config.embedding_model,
            embedding_dim=self.config.embedding_dim,
            embedding_layers=self.config.embedding_layers,
        )
        self._engine = HybridSearchEngine(self.config)
        self._pipeline = IndexingPipeline(
            self.config,
            search_engine=self._engine,
            embedder=self._embedder,
            store=self._store,
        )

        # Do NOT eagerly load the embedding model — it will load on first use.
        # This keeps daemon startup fast and memory-light.

        # Warm search engine with previously indexed data
        from desksearch.api.server import _warm_search_engine
        _warm_search_engine(self._engine, self._store, self._embedder, self.config)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, daemonize: bool = True) -> None:
        """Start the background service.

        Args:
            daemonize: If True, fork into the background (Unix only).
        """
        existing = self.read_pid()
        if existing:
            raise RuntimeError(
                f"DeskSearch daemon is already running (PID {existing}). "
                "Stop it first with 'desksearch daemon stop'."
            )

        if daemonize and sys.platform != "win32":
            self._daemonize()

        _setup_logging()
        logger.info("Starting DeskSearch daemon (PID %d)", os.getpid())
        self._start_time = datetime.now(timezone.utc)
        self._write_pid()

        # Apply resource limits (nice level, memory cap)
        self._apply_resource_limits()

        # Install signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        try:
            self._init_pipeline()
            self._start_server()
            self._start_watcher()

            # Start queue processor
            queue_thread = threading.Thread(
                target=self._process_queue, daemon=True, name="queue-processor",
            )
            queue_thread.start()

            # Start resource monitor
            monitor_thread = threading.Thread(
                target=self._monitor_resources, daemon=True, name="resource-monitor",
            )
            monitor_thread.start()

            self._write_health()
            logger.info(
                "DeskSearch daemon fully started (max_memory=%dMB, nice=%d)",
                self.max_memory_mb, DEFAULT_NICE_LEVEL,
            )

            # Main loop — just wait for shutdown
            while not self._shutdown_event.is_set():
                self._shutdown_event.wait(timeout=30.0)
                self._write_health()

        except Exception:
            logger.exception("Fatal error in daemon")
            raise
        finally:
            self._cleanup()

    def stop(self) -> None:
        """Signal the daemon to stop."""
        self._shutdown_event.set()

    def _signal_handler(self, signum: int, frame) -> None:
        signame = signal.Signals(signum).name
        logger.info("Received %s, shutting down...", signame)
        self._shutdown_event.set()

    def _cleanup(self) -> None:
        """Clean up resources on shutdown."""
        logger.info("Cleaning up...")
        if self._watcher:
            try:
                self._watcher.stop()
            except Exception:
                logger.exception("Error stopping watcher")

        if self._server:
            self._server.should_exit = True

        # Unload embedding model to free memory
        if self._embedder:
            try:
                self._embedder.cooldown()
            except Exception:
                logger.exception("Error unloading embedder")

        if self._pipeline:
            try:
                self._pipeline.close()
            except Exception:
                logger.exception("Error closing pipeline")

        if self._store:
            try:
                self._store.close()
            except Exception:
                logger.exception("Error closing store")

        self._remove_pid()
        HEALTH_FILE.unlink(missing_ok=True)
        logger.info("DeskSearch daemon stopped")

    def _daemonize(self) -> None:
        """Fork the process into the background (Unix double-fork)."""
        # First fork
        pid = os.fork()
        if pid > 0:
            # Parent exits
            sys.exit(0)

        os.setsid()

        # Second fork
        pid = os.fork()
        if pid > 0:
            sys.exit(0)

        # Redirect std file descriptors to /dev/null
        sys.stdout.flush()
        sys.stderr.flush()
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, sys.stdin.fileno())
        os.dup2(devnull, sys.stdout.fileno())
        os.dup2(devnull, sys.stderr.fileno())
        os.close(devnull)

    # ------------------------------------------------------------------
    # Control helpers (called from CLI in the parent process)
    # ------------------------------------------------------------------

    @staticmethod
    def send_stop() -> bool:
        """Send SIGTERM to a running daemon. Returns True if signal sent."""
        pid = BackgroundService.read_pid()
        if pid is None:
            return False
        try:
            os.kill(pid, signal.SIGTERM)
            # Wait up to 5 seconds for process to exit
            for _ in range(50):
                try:
                    os.kill(pid, 0)
                    time.sleep(0.1)
                except OSError:
                    break
            PID_FILE.unlink(missing_ok=True)
            HEALTH_FILE.unlink(missing_ok=True)
            return True
        except OSError:
            PID_FILE.unlink(missing_ok=True)
            return False

    @staticmethod
    def get_status() -> Optional[dict]:
        """Read the health file and return status info, or None if not running."""
        pid = BackgroundService.read_pid()
        if pid is None:
            return None

        if HEALTH_FILE.exists():
            try:
                data = json.loads(HEALTH_FILE.read_text())
                data["pid"] = pid
                return data
            except (json.JSONDecodeError, OSError):
                pass

        return {"status": "running", "pid": pid}
