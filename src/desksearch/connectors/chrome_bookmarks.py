"""Connector for reading Chrome bookmarks.

Reads the Chrome Bookmarks JSON file, extracts URL, title, and folder
hierarchy.  Each bookmark becomes a ``Document`` with metadata.
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
from pathlib import Path
from typing import Any, Iterator, Optional

from desksearch.connectors.base import Connector
from desksearch.plugins.base import Document

logger = logging.getLogger(__name__)


def _default_chrome_bookmarks_path() -> Path | None:
    """Return the default Chrome Bookmarks file path for this OS."""
    system = platform.system()
    home = Path.home()
    candidates = {
        "Darwin": home / "Library/Application Support/Google/Chrome/Default/Bookmarks",
        "Linux": home / ".config/google-chrome/Default/Bookmarks",
        "Windows": home / "AppData/Local/Google/Chrome/User Data/Default/Bookmarks",
    }
    path = candidates.get(system)
    return path if path and path.exists() else None


class ChromeBookmarksConnector(Connector):
    """Import bookmarks from Chrome's Bookmarks JSON file."""

    @property
    def name(self) -> str:
        return "chrome-bookmarks"

    @property
    def description(self) -> str:
        return "Read bookmarks from Google Chrome and index URL, title, and folder."

    def __init__(self) -> None:
        super().__init__()
        self._bookmarks_path: Path | None = None

    def configure(self, config: dict[str, Any]) -> None:
        if "bookmarks_path" in config:
            self._bookmarks_path = Path(config["bookmarks_path"]).expanduser().resolve()
        else:
            self._bookmarks_path = _default_chrome_bookmarks_path()
        self._config = config

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        if "bookmarks_path" in config:
            p = Path(config["bookmarks_path"]).expanduser().resolve()
            if not p.is_file():
                errors.append(f"Bookmarks file not found: {config['bookmarks_path']}")
        return errors

    def fetch(self) -> Iterator[Document]:
        if self._bookmarks_path is None or not self._bookmarks_path.exists():
            logger.info("Chrome bookmarks file not found — skipping")
            return

        try:
            data = json.loads(self._bookmarks_path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to read Chrome bookmarks")
            return

        roots = data.get("roots", {})
        for root_node in roots.values():
            if isinstance(root_node, dict):
                yield from self._walk_node(root_node, folder_path="")

    def _walk_node(
        self, node: dict, folder_path: str
    ) -> Iterator[Document]:
        """Recursively walk the bookmark tree."""
        node_type = node.get("type", "")
        node_name = node.get("name", "")

        if node_type == "url":
            url = node.get("url", "")
            title = node_name or url
            uid = hashlib.sha256(url.encode()).hexdigest()[:16]

            content = f"{title}\n{url}"
            if folder_path:
                content += f"\nFolder: {folder_path}"

            yield Document(
                id=f"bookmark:chrome:{uid}",
                title=title,
                content=content,
                source="chrome-bookmarks",
                metadata={
                    "url": url,
                    "folder": folder_path,
                },
            )

        # Recurse into children (folders)
        current_path = (
            f"{folder_path}/{node_name}" if folder_path and node_name
            else node_name or folder_path
        )
        for child in node.get("children", []):
            yield from self._walk_node(child, folder_path=current_path)

    def schedule(self) -> Optional[str]:
        # Check bookmarks once a day
        return "0 3 * * *"
