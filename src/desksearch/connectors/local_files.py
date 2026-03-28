"""Connector for indexing local file directories.

Wraps the existing file-walking logic from the plugins system using the
adapter pattern, exposing it through the new ``Connector`` interface.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Iterator, Optional

from desksearch.connectors.base import Connector
from desksearch.plugins.base import Document

logger = logging.getLogger(__name__)

_DEFAULT_EXTENSIONS = {
    ".txt", ".md", ".pdf", ".docx", ".py", ".js", ".ts", ".html",
    ".json", ".yaml", ".yml", ".csv", ".rst", ".tex", ".ipynb",
    ".sh", ".toml", ".xml", ".eml", ".log", ".cfg", ".ini",
}

_DEFAULT_EXCLUDED = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", "dist", "build",
}


class LocalFilesConnector(Connector):
    """Scan local directories and yield files as indexable documents."""

    @property
    def name(self) -> str:
        return "local-files"

    @property
    def description(self) -> str:
        return "Scan local directories and surface files as indexable documents."

    def __init__(self) -> None:
        super().__init__()
        self._directories: list[Path] = []
        self._extensions: set[str] = set(_DEFAULT_EXTENSIONS)
        self._max_file_size_mb: int = 50
        self._excluded_dirs: set[str] = set(_DEFAULT_EXCLUDED)

    def configure(self, config: dict[str, Any]) -> None:
        raw_dirs = config.get("directories", [])
        self._directories = [Path(d).expanduser().resolve() for d in raw_dirs]

        if "extensions" in config:
            self._extensions = {
                ext if ext.startswith(".") else f".{ext}"
                for ext in config["extensions"]
            }
        if "max_file_size_mb" in config:
            self._max_file_size_mb = int(config["max_file_size_mb"])
        if "excluded_dirs" in config:
            self._excluded_dirs = set(config["excluded_dirs"])
        self._config = config

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        for d in config.get("directories", []):
            p = Path(d).expanduser().resolve()
            if not p.is_dir():
                errors.append(f"Directory not found: {d}")
        return errors

    def fetch(self) -> Iterator[Document]:
        max_bytes = self._max_file_size_mb * 1024 * 1024

        for directory in self._directories:
            if not directory.is_dir():
                logger.warning("Directory not found: %s", directory)
                continue

            for root, dirs, files in os.walk(directory):
                dirs[:] = [
                    d for d in dirs
                    if d not in self._excluded_dirs and not d.startswith(".")
                ]
                for fname in files:
                    fpath = Path(root) / fname
                    ext = fpath.suffix.lower()
                    if ext not in self._extensions:
                        continue
                    try:
                        stat = fpath.stat()
                        if stat.st_size > max_bytes or stat.st_size == 0:
                            continue
                    except OSError:
                        continue

                    uid = hashlib.sha256(str(fpath).encode()).hexdigest()[:16]
                    yield Document(
                        id=f"localfile:{uid}",
                        title=fname,
                        content=str(fpath),
                        source=str(directory),
                        metadata={
                            "path": str(fpath),
                            "size": stat.st_size,
                            "modified": stat.st_mtime,
                            "extension": ext,
                        },
                    )

    def schedule(self) -> Optional[str]:
        # Rescan every 6 hours by default
        return "0 */6 * * *" if self._directories else None
