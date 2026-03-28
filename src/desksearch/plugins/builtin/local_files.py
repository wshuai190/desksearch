"""Connector plugin for indexing arbitrary local file directories.

Unlike the core indexing pipeline (which is folder-based), this connector
provides a plugin-style wrapper that surfaces local files as ``Document``
objects. Useful for treating custom directories as a data source alongside
emails, bookmarks, etc.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

from desksearch.plugins.base import BaseConnectorPlugin, Document

logger = logging.getLogger(__name__)

# Default extensions to include when none are configured
_DEFAULT_EXTENSIONS = {
    ".txt", ".md", ".pdf", ".docx", ".py", ".js", ".ts", ".html",
    ".json", ".yaml", ".yml", ".csv", ".rst", ".tex", ".ipynb",
    ".sh", ".toml", ".xml", ".eml", ".log", ".cfg", ".ini",
}


class LocalFilesConnector(BaseConnectorPlugin):
    """Index files from one or more local directories.

    This wraps the simple pattern of walking directories, reading file
    metadata, and producing ``Document`` objects.  It does NOT parse file
    contents — that's the indexing pipeline's job.  Instead it emits
    lightweight documents with path/metadata so the pipeline can pick them up.
    """

    name = "local-files"
    version = "0.1.0"
    author = "DeskSearch"
    description = "Scan local directories and surface files as indexable documents."

    def __init__(self) -> None:
        self._directories: list[Path] = []
        self._extensions: set[str] = set(_DEFAULT_EXTENSIONS)
        self._max_file_size_mb: int = 50
        self._excluded_dirs: set[str] = {
            ".git", "__pycache__", "node_modules", ".venv", "venv",
            ".tox", ".mypy_cache", "dist", "build",
        }

    def setup(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
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

    def fetch(self) -> list[Document]:
        docs: list[Document] = []
        max_bytes = self._max_file_size_mb * 1024 * 1024

        for directory in self._directories:
            if not directory.is_dir():
                logger.warning("Local files directory not found: %s", directory)
                continue
            for root, dirs, files in os.walk(directory):
                # Prune excluded directories in-place
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
                        if stat.st_size > max_bytes:
                            continue
                        if stat.st_size == 0:
                            continue
                    except OSError:
                        continue

                    uid = hashlib.sha256(str(fpath).encode()).hexdigest()[:16]
                    docs.append(Document(
                        id=f"localfile:{uid}",
                        title=fname,
                        content=str(fpath),  # Pipeline will parse actual content
                        source=str(directory),
                        metadata={
                            "path": str(fpath),
                            "size": stat.st_size,
                            "modified": stat.st_mtime,
                            "extension": ext,
                        },
                    ))
        return docs
