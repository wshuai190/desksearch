"""Abstract base class for DeskSearch connectors.

A ``Connector`` is a data-source plugin that knows how to fetch documents
from an external (or local) source, track its own sync state, and optionally
provide a cron schedule for automatic syncing.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Iterator, Optional

from desksearch.plugins.base import Document


class Connector(ABC):
    """Abstract base for all data-source connectors.

    Subclasses must implement ``name``, ``description``, ``configure``,
    and ``fetch``.  Optionally override ``schedule`` and ``validate_config``.

    The base class provides automatic state tracking via ``status()``.
    """

    def __init__(self) -> None:
        self._enabled: bool = False
        self._last_sync: Optional[float] = None  # epoch timestamp
        self._doc_count: int = 0
        self._errors: list[str] = []
        self._config: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Abstract interface — subclasses MUST implement these
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this connector (e.g. 'local-files')."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this connector does."""

    @abstractmethod
    def configure(self, config: dict[str, Any]) -> None:
        """Apply configuration to this connector.

        Called when the user updates connector settings.  Implementations
        should validate and store whatever they need from *config*.

        Args:
            config: Connector-specific configuration dict.
        """

    @abstractmethod
    def fetch(self) -> Iterator[Document]:
        """Yield documents from the data source.

        This is the core method — it should iterate over the data source
        and yield ``Document`` objects.  Using an iterator (rather than
        returning a list) allows streaming large data sources without
        loading everything into memory.

        Yields:
            Document instances ready for indexing.
        """

    # ------------------------------------------------------------------
    # Optional overrides
    # ------------------------------------------------------------------

    def schedule(self) -> Optional[str]:
        """Return a cron expression for automatic periodic syncing.

        Override this to enable auto-sync.  Return ``None`` (default) to
        disable automatic syncing — the connector will only sync when
        triggered manually.

        Returns:
            Cron expression string (e.g. ``'0 */6 * * *'`` for every 6h),
            or ``None`` for manual-only.
        """
        return None

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        """Validate configuration before applying it.

        Override to add validation logic.  Returns a list of error messages
        (empty list = valid).

        Args:
            config: Configuration dict to validate.

        Returns:
            List of validation error strings (empty if valid).
        """
        return []

    # ------------------------------------------------------------------
    # State tracking (managed by the base class)
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Return the current connector status.

        Returns:
            Dict with keys: ``enabled``, ``last_sync``, ``doc_count``,
            ``errors``, ``schedule``.
        """
        return {
            "enabled": self._enabled,
            "last_sync": self._last_sync,
            "doc_count": self._doc_count,
            "errors": list(self._errors),
            "schedule": self.schedule(),
        }

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def record_sync(self, doc_count: int, errors: list[str] | None = None) -> None:
        """Record the result of a sync operation.

        Called by the registry after ``fetch()`` completes.

        Args:
            doc_count: Number of documents fetched.
            errors: List of error messages (if any).
        """
        self._last_sync = time.time()
        self._doc_count = doc_count
        self._errors = errors or []

    def __repr__(self) -> str:
        status = "enabled" if self._enabled else "disabled"
        return f"<{self.__class__.__name__} '{self.name}' ({status})>"
