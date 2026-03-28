"""Connector registry — discovers, manages, and syncs connectors."""

from __future__ import annotations

import logging
from typing import Any, Iterator

from desksearch.connectors.base import Connector
from desksearch.plugins.base import Document

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    """Central registry for connector instances.

    Handles discovery, configuration, enable/disable, and sync orchestration.
    """

    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, connector: Connector) -> None:
        """Register a connector instance."""
        if connector.name in self._connectors:
            logger.warning(
                "Connector %r already registered — replacing", connector.name
            )
        self._connectors[connector.name] = connector
        logger.info("Registered connector: %s", connector.name)

    def unregister(self, name: str) -> bool:
        """Unregister a connector by name. Returns True if it existed."""
        removed = self._connectors.pop(name, None)
        if removed is not None:
            logger.info("Unregistered connector: %s", name)
            return True
        return False

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> None:
        """Auto-discover and register all built-in connectors."""
        from desksearch.connectors.local_files import LocalFilesConnector
        from desksearch.connectors.email_mbox import EmailMboxConnector
        from desksearch.connectors.chrome_bookmarks import ChromeBookmarksConnector
        from desksearch.connectors.slack_export import SlackExportConnector

        for cls in (
            LocalFilesConnector,
            EmailMboxConnector,
            ChromeBookmarksConnector,
            SlackExportConnector,
        ):
            try:
                instance = cls()
                self.register(instance)
            except Exception:
                logger.exception(
                    "Failed to instantiate connector: %s", cls.__name__
                )

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get(self, name: str) -> Connector | None:
        """Get a connector by name."""
        return self._connectors.get(name)

    def all(self) -> dict[str, Connector]:
        """Return all registered connectors (name → instance)."""
        return dict(self._connectors)

    def list_status(self) -> list[dict[str, Any]]:
        """Return status dicts for all connectors."""
        result = []
        for name, connector in self._connectors.items():
            status = connector.status()
            status["name"] = name
            status["description"] = connector.description
            result.append(status)
        return result

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def enable(self, name: str) -> bool:
        """Enable a connector. Returns False if not found."""
        conn = self._connectors.get(name)
        if conn is None:
            return False
        conn.enabled = True
        logger.info("Enabled connector: %s", name)
        return True

    def disable(self, name: str) -> bool:
        """Disable a connector. Returns False if not found."""
        conn = self._connectors.get(name)
        if conn is None:
            return False
        conn.enabled = False
        logger.info("Disabled connector: %s", name)
        return True

    def configure(self, name: str, config: dict[str, Any]) -> list[str]:
        """Configure a connector. Returns validation errors (empty = success)."""
        conn = self._connectors.get(name)
        if conn is None:
            return [f"Unknown connector: {name}"]

        errors = conn.validate_config(config)
        if errors:
            return errors

        conn.configure(config)
        return []

    def sync(self, name: str) -> tuple[list[Document], list[str]]:
        """Trigger a sync for a specific connector.

        Returns:
            Tuple of (documents, errors).
        """
        conn = self._connectors.get(name)
        if conn is None:
            return [], [f"Unknown connector: {name}"]

        docs: list[Document] = []
        errors: list[str] = []

        try:
            for doc in conn.fetch():
                docs.append(doc)
        except Exception as exc:
            logger.exception("Connector %s fetch failed", name)
            errors.append(str(exc))

        conn.record_sync(len(docs), errors)
        return docs, errors

    def sync_all_enabled(self) -> dict[str, tuple[list[Document], list[str]]]:
        """Sync all enabled connectors. Returns {name: (docs, errors)}."""
        results = {}
        for name, conn in self._connectors.items():
            if conn.enabled:
                results[name] = self.sync(name)
        return results

    def __len__(self) -> int:
        return len(self._connectors)

    def __repr__(self) -> str:
        enabled = sum(1 for c in self._connectors.values() if c.enabled)
        return f"<ConnectorRegistry total={len(self._connectors)} enabled={enabled}>"
