"""Connector plugin that indexes text copied to the system clipboard."""

from __future__ import annotations

import hashlib
import logging
import subprocess
import platform
from typing import Any

from desksearch.plugins.base import BaseConnectorPlugin, Document

logger = logging.getLogger(__name__)


def _get_clipboard_text() -> str | None:
    """Read current clipboard contents using platform utilities."""
    system = platform.system()
    try:
        if system == "Darwin":
            return subprocess.check_output(["pbpaste"], text=True)
        elif system == "Linux":
            return subprocess.check_output(
                ["xclip", "-selection", "clipboard", "-o"], text=True
            )
        elif system == "Windows":
            return subprocess.check_output(
                ["powershell", "-command", "Get-Clipboard"], text=True
            )
    except FileNotFoundError:
        logger.debug("Clipboard utility not found on %s", system)
    except subprocess.CalledProcessError:
        logger.debug("Clipboard read failed")
    return None


class ClipboardMonitor(BaseConnectorPlugin):
    """Capture clipboard text and present it as indexable documents.

    Each call to ``fetch()`` reads the current clipboard and returns it as a
    single document (if non-empty and not already seen).  A calling loop can
    invoke ``sync()`` periodically to build up a history.
    """

    name = "clipboard-monitor"
    version = "0.1.0"
    author = "DeskSearch"
    description = "Watch the system clipboard and index copied text snippets."

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._max_history: int = 500

    def setup(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self._max_history = config.get("max_history", 500)

    def fetch(self) -> list[Document]:
        text = _get_clipboard_text()
        if not text or not text.strip():
            return []
        text = text.strip()
        digest = hashlib.sha256(text.encode()).hexdigest()[:16]
        if digest in self._seen:
            return []
        self._seen.add(digest)
        # Evict oldest entries when history is full.
        if len(self._seen) > self._max_history:
            self._seen = set(list(self._seen)[-self._max_history :])
        title = text[:80].replace("\n", " ")
        return [
            Document(
                id=f"clipboard:{digest}",
                title=title,
                content=text,
                source="clipboard",
            )
        ]

    def sync(self) -> list[Document]:
        return self.fetch()
