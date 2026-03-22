"""Plugin registry — the central catalogue of loaded plugins."""

from __future__ import annotations

import logging
from typing import Any

from desksearch.plugins.base import (
    BaseConnectorPlugin,
    BaseParserPlugin,
    BasePlugin,
    BaseSearchPlugin,
)

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Stores and retrieves loaded plugin instances by kind."""

    def __init__(self) -> None:
        self._parsers: dict[str, BaseParserPlugin] = {}
        self._search: dict[str, BaseSearchPlugin] = {}
        self._connectors: dict[str, BaseConnectorPlugin] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        plugin: BasePlugin,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Register a plugin instance (calls ``setup`` automatically)."""
        try:
            plugin.setup(config)
        except Exception:
            logger.exception("Plugin %s failed during setup — skipping", plugin.name)
            return

        if isinstance(plugin, BaseParserPlugin):
            self._parsers[plugin.name] = plugin
            logger.info("Registered parser plugin: %s", plugin.name)
        elif isinstance(plugin, BaseSearchPlugin):
            self._search[plugin.name] = plugin
            logger.info("Registered search plugin: %s", plugin.name)
        elif isinstance(plugin, BaseConnectorPlugin):
            self._connectors[plugin.name] = plugin
            logger.info("Registered connector plugin: %s", plugin.name)
        else:
            logger.warning(
                "Plugin %s does not subclass a known plugin type — skipping",
                plugin.name,
            )

    def unregister(self, name: str) -> None:
        """Unregister a plugin by name (calls ``teardown``)."""
        for store in (self._parsers, self._search, self._connectors):
            plugin = store.pop(name, None)
            if plugin is not None:
                try:
                    plugin.teardown()
                except Exception:
                    logger.exception("Error during teardown of plugin %s", name)
                return
        logger.warning("Plugin %s not found in registry", name)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def parsers(self) -> dict[str, BaseParserPlugin]:
        return dict(self._parsers)

    @property
    def search_plugins(self) -> dict[str, BaseSearchPlugin]:
        return dict(self._search)

    @property
    def connectors(self) -> dict[str, BaseConnectorPlugin]:
        return dict(self._connectors)

    def get_parser_for_ext(self, ext: str) -> BaseParserPlugin | None:
        """Find a parser plugin that handles the given extension."""
        ext = ext.lower()
        for parser in self._parsers.values():
            if ext in [e.lower() for e in parser.extensions]:
                return parser
        return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def teardown_all(self) -> None:
        """Teardown every registered plugin."""
        for store in (self._parsers, self._search, self._connectors):
            for plugin in store.values():
                try:
                    plugin.teardown()
                except Exception:
                    logger.exception("Error during teardown of plugin %s", plugin.name)
            store.clear()

    def __repr__(self) -> str:
        counts = (
            f"parsers={len(self._parsers)}, "
            f"search={len(self._search)}, "
            f"connectors={len(self._connectors)}"
        )
        return f"<PluginRegistry {counts}>"
