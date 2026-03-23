"""Filesystem watcher for detecting file changes.

Uses watchdog to monitor configured directories and trigger re-indexing
when files are created, modified, or deleted.

Debouncing: after a filesystem event, waits 2 seconds of quiet time before
triggering callbacks. Multiple events for different files within the quiet
period are batched together.
"""
import logging
import threading
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from desksearch.config import Config

logger = logging.getLogger(__name__)

# Seconds to wait after the last event before processing the batch.
DEBOUNCE_SECONDS = 2.0


class IndexEventHandler(FileSystemEventHandler):
    """Handles filesystem events with debouncing and batching.

    Events are accumulated into per-file buckets. After DEBOUNCE_SECONDS of
    quiet time (no new events for *any* file), the entire batch is dispatched.
    """

    def __init__(
        self,
        config: Config,
        on_created_cb: Optional[Callable[[Path], None]] = None,
        on_modified_cb: Optional[Callable[[Path], None]] = None,
        on_deleted_cb: Optional[Callable[[Path], None]] = None,
    ) -> None:
        self.config = config
        self._on_created_cb = on_created_cb
        self._on_modified_cb = on_modified_cb
        self._on_deleted_cb = on_deleted_cb
        self._extensions = set(config.file_extensions)
        self._excluded = set(config.excluded_dirs)

        # Debouncing state
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None
        # Pending events: path -> event_type (last event wins per path)
        self._pending: dict[Path, str] = {}
        self.events_processed = 0

    def _should_process(self, path: Path) -> bool:
        """Check if the file should be processed based on config filters."""
        if path.suffix.lower() not in self._extensions:
            return False
        for part in path.parts:
            if part in self._excluded:
                return False
        return True

    def _schedule_flush(self) -> None:
        """Reset the debounce timer. Called under self._lock."""
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(DEBOUNCE_SECONDS, self._flush)
        self._timer.daemon = True
        self._timer.start()

    def _flush(self) -> None:
        """Process all pending events after the debounce period."""
        with self._lock:
            batch = dict(self._pending)
            self._pending.clear()
            self._timer = None

        for path, event_type in batch.items():
            try:
                if event_type == "created" and self._on_created_cb:
                    logger.info("File created (debounced): %s", path)
                    self._on_created_cb(path)
                elif event_type == "modified" and self._on_modified_cb:
                    logger.info("File modified (debounced): %s", path)
                    self._on_modified_cb(path)
                elif event_type == "deleted" and self._on_deleted_cb:
                    logger.info("File deleted (debounced): %s", path)
                    self._on_deleted_cb(path)
            except Exception:
                logger.exception("Error processing %s event for %s", event_type, path)
            self.events_processed += 1

    def _enqueue(self, path: Path, event_type: str) -> None:
        """Add an event to the pending batch and reset the debounce timer."""
        with self._lock:
            self._pending[path] = event_type
            self._schedule_flush()

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if self._should_process(path):
            self._enqueue(path, "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if self._should_process(path):
            self._enqueue(path, "modified")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if self._should_process(path):
            self._enqueue(path, "deleted")

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle rename/move as delete old + create new."""
        if event.is_directory:
            return
        old_path = Path(event.src_path)
        new_path = Path(event.dest_path)
        if self._should_process(old_path):
            self._enqueue(old_path, "deleted")
        if self._should_process(new_path):
            self._enqueue(new_path, "created")


class FileWatcher:
    """Watches directories for file changes and triggers callbacks."""

    def __init__(
        self,
        config: Config,
        on_created: Optional[Callable[[Path], None]] = None,
        on_modified: Optional[Callable[[Path], None]] = None,
        on_deleted: Optional[Callable[[Path], None]] = None,
    ) -> None:
        self.config = config
        self._observer = Observer()
        self._handler = IndexEventHandler(
            config,
            on_created_cb=on_created,
            on_modified_cb=on_modified,
            on_deleted_cb=on_deleted,
        )
        self._running = False
        self._watched_paths: list[str] = []

    def start(self) -> None:
        """Start watching all configured directories."""
        for path in self.config.index_paths:
            if path.exists() and path.is_dir():
                self._observer.schedule(self._handler, str(path), recursive=True)
                self._watched_paths.append(str(path))
                logger.info("Watching directory: %s", path)
            else:
                logger.warning("Skipping non-existent directory: %s", path)
        self._observer.start()
        self._running = True
        logger.info("File watcher started")

    def stop(self) -> None:
        """Stop watching."""
        if self._running:
            # Cancel any pending debounce timer
            with self._handler._lock:
                if self._handler._timer is not None:
                    self._handler._timer.cancel()
                    self._handler._timer = None
            self._observer.stop()
            self._observer.join()
            self._running = False
            logger.info("File watcher stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def watched_paths(self) -> list[str]:
        return list(self._watched_paths)

    @property
    def events_processed(self) -> int:
        return self._handler.events_processed
