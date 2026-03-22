"""Filesystem watcher for detecting file changes.

Uses watchdog to monitor configured directories and trigger re-indexing
when files are created, modified, or deleted.
"""
import logging
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from desksearch.config import Config

logger = logging.getLogger(__name__)


class IndexEventHandler(FileSystemEventHandler):
    """Handles filesystem events and dispatches to indexing callbacks."""

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

    def _should_process(self, path: Path) -> bool:
        """Check if the file should be processed based on config filters."""
        if path.suffix.lower() not in self._extensions:
            return False
        for part in path.parts:
            if part in self._excluded:
                return False
        return True

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if self._should_process(path) and self._on_created_cb:
            logger.info("File created: %s", path)
            self._on_created_cb(path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if self._should_process(path) and self._on_modified_cb:
            logger.info("File modified: %s", path)
            self._on_modified_cb(path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if self._should_process(path) and self._on_deleted_cb:
            logger.info("File deleted: %s", path)
            self._on_deleted_cb(path)


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

    def start(self) -> None:
        """Start watching all configured directories."""
        for path in self.config.index_paths:
            if path.exists() and path.is_dir():
                self._observer.schedule(self._handler, str(path), recursive=True)
                logger.info("Watching directory: %s", path)
            else:
                logger.warning("Skipping non-existent directory: %s", path)
        self._observer.start()
        self._running = True
        logger.info("File watcher started")

    def stop(self) -> None:
        """Stop watching."""
        if self._running:
            self._observer.stop()
            self._observer.join()
            self._running = False
            logger.info("File watcher stopped")

    @property
    def is_running(self) -> bool:
        return self._running
