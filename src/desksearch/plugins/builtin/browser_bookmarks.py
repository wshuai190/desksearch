"""Connector plugin for reading browser bookmarks (Chrome & Firefox)."""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import sqlite3
import shutil
import tempfile
from pathlib import Path
from typing import Any

from desksearch.plugins.base import BaseConnectorPlugin, Document

logger = logging.getLogger(__name__)


def _default_chrome_bookmarks_path() -> Path | None:
    system = platform.system()
    home = Path.home()
    candidates = {
        "Darwin": home / "Library/Application Support/Google/Chrome/Default/Bookmarks",
        "Linux": home / ".config/google-chrome/Default/Bookmarks",
        "Windows": home / "AppData/Local/Google/Chrome/User Data/Default/Bookmarks",
    }
    path = candidates.get(system)
    return path if path and path.exists() else None


def _default_firefox_places_path() -> Path | None:
    system = platform.system()
    home = Path.home()
    profile_roots = {
        "Darwin": home / "Library/Application Support/Firefox/Profiles",
        "Linux": home / ".mozilla/firefox",
        "Windows": home / "AppData/Roaming/Mozilla/Firefox/Profiles",
    }
    root = profile_roots.get(system)
    if not root or not root.is_dir():
        return None
    for profile_dir in root.iterdir():
        places = profile_dir / "places.sqlite"
        if places.exists():
            return places
    return None


class BrowserBookmarksConnector(BaseConnectorPlugin):
    """Index bookmarks from Chrome and Firefox."""

    name = "browser-bookmarks"
    version = "0.1.0"
    author = "DeskSearch"
    description = "Read bookmarks from Chrome and Firefox and index them."

    def __init__(self) -> None:
        self._chrome_path: Path | None = None
        self._firefox_path: Path | None = None

    def setup(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        if "chrome_bookmarks" in config:
            self._chrome_path = Path(config["chrome_bookmarks"]).expanduser()
        else:
            self._chrome_path = _default_chrome_bookmarks_path()
        if "firefox_places" in config:
            self._firefox_path = Path(config["firefox_places"]).expanduser()
        else:
            self._firefox_path = _default_firefox_places_path()

    # ------------------------------------------------------------------

    def fetch(self) -> list[Document]:
        docs: list[Document] = []
        docs.extend(self._chrome_bookmarks())
        docs.extend(self._firefox_bookmarks())
        return docs

    # ------------------------------------------------------------------

    def _chrome_bookmarks(self) -> list[Document]:
        if not self._chrome_path or not self._chrome_path.exists():
            return []
        try:
            data = json.loads(self._chrome_path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to read Chrome bookmarks")
            return []

        docs: list[Document] = []

        def _walk(node: dict) -> None:
            if node.get("type") == "url":
                url = node.get("url", "")
                title = node.get("name", url)
                uid = hashlib.sha256(url.encode()).hexdigest()[:16]
                docs.append(Document(
                    id=f"bookmark:chrome:{uid}",
                    title=title,
                    content=f"{title}\n{url}",
                    source="chrome",
                    metadata={"url": url},
                ))
            for child in node.get("children", []):
                _walk(child)

        for root_node in data.get("roots", {}).values():
            if isinstance(root_node, dict):
                _walk(root_node)
        return docs

    def _firefox_bookmarks(self) -> list[Document]:
        if not self._firefox_path or not self._firefox_path.exists():
            return []
        docs: list[Document] = []
        # Firefox locks places.sqlite — copy to a temp file to read safely.
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()
        try:
            shutil.copy2(self._firefox_path, tmp_path)
            conn = sqlite3.connect(str(tmp_path))
            try:
                cursor = conn.execute(
                    "SELECT mb.title, mp.url FROM moz_bookmarks mb "
                    "JOIN moz_places mp ON mb.fk = mp.id "
                    "WHERE mp.url NOT LIKE 'place:%'"
                )
                for title, url in cursor.fetchall():
                    title = title or url
                    uid = hashlib.sha256(url.encode()).hexdigest()[:16]
                    docs.append(Document(
                        id=f"bookmark:firefox:{uid}",
                        title=title,
                        content=f"{title}\n{url}",
                        source="firefox",
                        metadata={"url": url},
                    ))
            finally:
                conn.close()
        except Exception:
            logger.exception("Failed to read Firefox bookmarks")
        finally:
            tmp_path.unlink(missing_ok=True)
        return docs
