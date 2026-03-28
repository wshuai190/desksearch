"""Built-in plugins shipped with DeskSearch.

Connectors:
  - BrowserBookmarksConnector — Chrome & Firefox bookmarks
  - ClipboardMonitor — system clipboard text
  - EmailConnector — .eml and .mbox files
  - LocalFilesConnector — arbitrary local directories
  - SlackExportConnector — Slack workspace exports
"""

from desksearch.plugins.builtin.browser_bookmarks import BrowserBookmarksConnector
from desksearch.plugins.builtin.clipboard_monitor import ClipboardMonitor
from desksearch.plugins.builtin.email_connector import EmailConnector
from desksearch.plugins.builtin.local_files import LocalFilesConnector
from desksearch.plugins.builtin.slack_export import SlackExportConnector

ALL_BUILTIN_CONNECTORS = [
    BrowserBookmarksConnector,
    ClipboardMonitor,
    EmailConnector,
    LocalFilesConnector,
    SlackExportConnector,
]

__all__ = [
    "BrowserBookmarksConnector",
    "ClipboardMonitor",
    "EmailConnector",
    "LocalFilesConnector",
    "SlackExportConnector",
    "ALL_BUILTIN_CONNECTORS",
]
