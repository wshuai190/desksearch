"""DeskSearch connector system — plugin architecture for custom data sources.

This package provides a higher-level connector framework on top of the core
plugin system, adding:

- ``Connector`` ABC with ``schedule()``, ``status()``, and ``configure()``
- ``ConnectorRegistry`` with state tracking (enabled, last_sync, doc_count, errors)
- Built-in connectors: local files, email/mbox, Chrome bookmarks, Slack export

Usage::

    from desksearch.connectors import ConnectorRegistry

    registry = ConnectorRegistry()
    registry.discover()  # auto-discovers all built-in connectors

    for name, connector in registry.all().items():
        print(connector.name, connector.status())
"""

from desksearch.connectors.base import Connector
from desksearch.connectors.registry import ConnectorRegistry

__all__ = [
    "Connector",
    "ConnectorRegistry",
]
