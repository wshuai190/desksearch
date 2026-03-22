"""DeskSearch plugin system.

Public API
----------
- ``BasePlugin``, ``BaseParserPlugin``, ``BaseSearchPlugin``,
  ``BaseConnectorPlugin``, ``Document`` — base classes for plugin authors.
- ``PluginRegistry`` — discovers, loads, and manages plugins.
"""

from desksearch.plugins.base import (
    BaseConnectorPlugin,
    BaseParserPlugin,
    BasePlugin,
    BaseSearchPlugin,
    Document,
)
from desksearch.plugins.registry import PluginRegistry

__all__ = [
    "BasePlugin",
    "BaseParserPlugin",
    "BaseSearchPlugin",
    "BaseConnectorPlugin",
    "Document",
    "PluginRegistry",
]
