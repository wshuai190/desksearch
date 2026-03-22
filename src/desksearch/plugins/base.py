"""Abstract base classes for DeskSearch plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Document:
    """A document produced by a connector plugin."""

    id: str
    title: str
    content: str
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class BasePlugin(ABC):
    """Base class every plugin must inherit from."""

    name: str = "unnamed"
    version: str = "0.1.0"
    author: str = "unknown"
    description: str = ""

    def setup(self, config: dict[str, Any] | None = None) -> None:
        """Called once when the plugin is loaded. Override for init logic."""

    def teardown(self) -> None:
        """Called when the plugin is unloaded. Override for cleanup."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name}@{self.version}>"


class BaseParserPlugin(BasePlugin):
    """Plugin that adds support for parsing new file types.

    Subclasses must set ``extensions`` and implement ``parse``.
    """

    extensions: list[str] = []
    """File extensions this parser handles (e.g. ['.epub', '.pptx'])."""

    @abstractmethod
    def parse(self, file_path: Path) -> str:
        """Extract plain text from *file_path*.

        Returns:
            Extracted text content.

        Raises:
            Any exception — the caller will log and skip the file.
        """


class BaseSearchPlugin(BasePlugin):
    """Plugin that can rerank or post-process search results.

    ``rerank`` receives the query and the current result list and must return
    a (possibly reordered/filtered) result list.
    """

    @abstractmethod
    def rerank(
        self,
        query: str,
        results: list[Any],
    ) -> list[Any]:
        """Rerank or filter *results* for the given *query*."""


class BaseConnectorPlugin(BasePlugin):
    """Plugin that fetches documents from an external data source.

    Connectors are used during indexing to pull data from places like Gmail,
    Slack, Notion, browser bookmarks, etc.
    """

    @abstractmethod
    def fetch(self) -> list[Document]:
        """Fetch all documents from the data source.

        Returns:
            Full list of documents currently available.
        """

    def sync(self) -> list[Document]:
        """Fetch only new or updated documents since the last sync.

        The default implementation falls back to ``fetch()``.
        """
        return self.fetch()
