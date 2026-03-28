"""Tests for the connector plugin system.

Covers:
  - Base classes and Document model
  - Plugin registry (register, unregister, accessors)
  - Plugin loader (entry points + local plugins)
  - Built-in connectors:
    * BrowserBookmarksConnector (Chrome + Firefox)
    * ClipboardMonitor
    * EmailConnector (.eml + .mbox)
    * LocalFilesConnector
    * SlackExportConnector
  - Connector API endpoints (/api/connectors, sync, config)
"""

from __future__ import annotations

import json
import mailbox
import os
import shutil
import tempfile
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from desksearch.plugins.base import (
    BaseConnectorPlugin,
    BaseParserPlugin,
    BasePlugin,
    BaseSearchPlugin,
    Document,
)
from desksearch.plugins.registry import PluginRegistry


# ───────────────────────── Document Model ─────────────────────────


class TestDocument:
    """Test the Document dataclass."""

    def test_create_basic(self):
        doc = Document(id="test:1", title="Test", content="Hello world")
        assert doc.id == "test:1"
        assert doc.title == "Test"
        assert doc.content == "Hello world"
        assert doc.source == ""
        assert doc.metadata == {}

    def test_create_with_metadata(self):
        doc = Document(
            id="email:abc",
            title="Meeting notes",
            content="Body text",
            source="gmail",
            metadata={"from": "user@example.com", "date": "2025-01-01"},
        )
        assert doc.source == "gmail"
        assert doc.metadata["from"] == "user@example.com"

    def test_immutable(self):
        doc = Document(id="x", title="T", content="C")
        with pytest.raises(AttributeError):
            doc.id = "y"  # type: ignore

    def test_equality(self):
        a = Document(id="1", title="A", content="C")
        b = Document(id="1", title="A", content="C")
        assert a == b


# ───────────────────────── Base Classes ─────────────────────────


class TestBaseClasses:
    """Test abstract base classes."""

    def test_base_plugin_repr(self):
        class MyPlugin(BasePlugin):
            name = "my-plugin"
            version = "1.0.0"

        p = MyPlugin()
        assert "my-plugin" in repr(p)
        assert "1.0.0" in repr(p)

    def test_base_plugin_setup_teardown(self):
        class MyPlugin(BasePlugin):
            name = "test"

        p = MyPlugin()
        p.setup({"key": "value"})  # should not raise
        p.teardown()  # should not raise

    def test_connector_must_implement_fetch(self):
        with pytest.raises(TypeError):
            # Can't instantiate abstract class
            BaseConnectorPlugin()  # type: ignore

    def test_connector_sync_falls_back_to_fetch(self):
        class TestConnector(BaseConnectorPlugin):
            name = "test"

            def fetch(self):
                return [Document(id="1", title="T", content="C")]

        c = TestConnector()
        assert len(c.sync()) == 1

    def test_parser_must_implement_parse(self):
        with pytest.raises(TypeError):
            BaseParserPlugin()  # type: ignore

    def test_search_plugin_must_implement_rerank(self):
        with pytest.raises(TypeError):
            BaseSearchPlugin()  # type: ignore


# ───────────────────────── Plugin Registry ─────────────────────────


class TestPluginRegistry:
    """Test the plugin registry."""

    def _make_connector(self, name="test-connector"):
        class C(BaseConnectorPlugin):
            version = "0.1.0"

            def fetch(self):
                return []

        c = C()
        c.name = name
        return c

    def _make_parser(self, name="test-parser"):
        class P(BaseParserPlugin):
            extensions = [".xyz"]

            def parse(self, file_path):
                return ""

        p = P()
        p.name = name
        return p

    def _make_search_plugin(self, name="test-search"):
        class S(BaseSearchPlugin):
            def rerank(self, query, results):
                return results

        s = S()
        s.name = name
        return s

    def test_register_connector(self):
        reg = PluginRegistry()
        c = self._make_connector()
        reg.register(c)
        assert "test-connector" in reg.connectors
        assert len(reg.parsers) == 0

    def test_register_parser(self):
        reg = PluginRegistry()
        p = self._make_parser()
        reg.register(p)
        assert "test-parser" in reg.parsers

    def test_register_search(self):
        reg = PluginRegistry()
        s = self._make_search_plugin()
        reg.register(s)
        assert "test-search" in reg.search_plugins

    def test_get_parser_for_ext(self):
        reg = PluginRegistry()
        p = self._make_parser()
        reg.register(p)
        found = reg.get_parser_for_ext(".xyz")
        assert found is not None
        assert found.name == "test-parser"
        assert reg.get_parser_for_ext(".nope") is None

    def test_unregister(self):
        reg = PluginRegistry()
        c = self._make_connector()
        reg.register(c)
        assert "test-connector" in reg.connectors
        reg.unregister("test-connector")
        assert "test-connector" not in reg.connectors

    def test_unregister_nonexistent(self):
        reg = PluginRegistry()
        reg.unregister("nonexistent")  # should not raise

    def test_teardown_all(self):
        reg = PluginRegistry()
        c = self._make_connector()
        p = self._make_parser()
        reg.register(c)
        reg.register(p)
        reg.teardown_all()
        assert len(reg.connectors) == 0
        assert len(reg.parsers) == 0

    def test_setup_failure_skips_plugin(self):
        class BadConnector(BaseConnectorPlugin):
            name = "bad"

            def setup(self, config=None):
                raise RuntimeError("setup failed")

            def fetch(self):
                return []

        reg = PluginRegistry()
        reg.register(BadConnector())
        assert "bad" not in reg.connectors

    def test_repr(self):
        reg = PluginRegistry()
        s = repr(reg)
        assert "PluginRegistry" in s
        assert "parsers=0" in s

    def test_register_with_config(self):
        received_config = {}

        class ConfigConnector(BaseConnectorPlugin):
            name = "cfg"

            def setup(self, config=None):
                received_config.update(config or {})

            def fetch(self):
                return []

        reg = PluginRegistry()
        reg.register(ConfigConnector(), config={"key": "value"})
        assert received_config == {"key": "value"}
        assert "cfg" in reg.connectors


# ───────────────────────── Plugin Loader ─────────────────────────


class TestPluginLoader:
    """Test plugin discovery from local directory."""

    def test_load_local_plugins(self):
        from desksearch.plugins.loader import _load_local_plugins

        with tempfile.TemporaryDirectory() as d:
            # Write a simple plugin file
            plugin_code = '''
from desksearch.plugins.base import BaseConnectorPlugin, Document

class TestLocalPlugin(BaseConnectorPlugin):
    name = "test-local"
    version = "0.1.0"
    description = "Test local plugin"

    def fetch(self):
        return [Document(id="local:1", title="Local", content="Test")]
'''
            (Path(d) / "my_plugin.py").write_text(plugin_code)

            plugins = _load_local_plugins(Path(d))
            assert len(plugins) >= 1
            names = [p().name for p in plugins]
            assert "test-local" in names

    def test_load_local_plugins_skips_underscore(self):
        from desksearch.plugins.loader import _load_local_plugins

        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "_helper.py").write_text("# helper file")
            plugins = _load_local_plugins(Path(d))
            assert len(plugins) == 0

    def test_load_local_plugins_nonexistent_dir(self):
        from desksearch.plugins.loader import _load_local_plugins

        plugins = _load_local_plugins(Path("/nonexistent/path"))
        assert plugins == []

    def test_discover_plugins_with_enabled_filter(self):
        from desksearch.plugins.loader import discover_plugins

        with tempfile.TemporaryDirectory() as d:
            plugin_code = '''
from desksearch.plugins.base import BaseConnectorPlugin, Document

class PluginA(BaseConnectorPlugin):
    name = "plugin-a"
    def fetch(self):
        return []

class PluginB(BaseConnectorPlugin):
    name = "plugin-b"
    def fetch(self):
        return []
'''
            (Path(d) / "plugins.py").write_text(plugin_code)

            reg = discover_plugins(
                enabled=["plugin-a"],
                local_dir=Path(d),
            )
            assert "plugin-a" in reg.connectors
            assert "plugin-b" not in reg.connectors


# ───────────────────────── Browser Bookmarks Connector ─────────────────────────


class TestBrowserBookmarksConnector:
    """Test the Chrome/Firefox bookmarks connector."""

    def test_chrome_bookmarks(self):
        from desksearch.plugins.builtin.browser_bookmarks import BrowserBookmarksConnector

        with tempfile.TemporaryDirectory() as d:
            bookmarks = {
                "roots": {
                    "bookmark_bar": {
                        "type": "folder",
                        "children": [
                            {
                                "type": "url",
                                "name": "Example",
                                "url": "https://example.com",
                            },
                            {
                                "type": "url",
                                "name": "Test Site",
                                "url": "https://test.example.org/page",
                            },
                        ],
                    }
                }
            }
            bk_path = Path(d) / "Bookmarks"
            bk_path.write_text(json.dumps(bookmarks))

            connector = BrowserBookmarksConnector()
            connector.setup({"chrome_bookmarks": str(bk_path)})
            docs = connector.fetch()

            assert len(docs) == 2
            assert all(d.id.startswith("bookmark:chrome:") for d in docs)
            assert any("Example" in d.title for d in docs)
            assert any("test.example.org" in d.content for d in docs)

    def test_firefox_bookmarks(self):
        import sqlite3

        from desksearch.plugins.builtin.browser_bookmarks import BrowserBookmarksConnector

        with tempfile.TemporaryDirectory() as d:
            db_path = Path(d) / "places.sqlite"
            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT)"
            )
            conn.execute(
                "CREATE TABLE moz_bookmarks (id INTEGER PRIMARY KEY, fk INTEGER, title TEXT)"
            )
            conn.execute(
                "INSERT INTO moz_places (id, url) VALUES (1, 'https://mozilla.org')"
            )
            conn.execute(
                "INSERT INTO moz_bookmarks (id, fk, title) VALUES (1, 1, 'Mozilla')"
            )
            conn.commit()
            conn.close()

            connector = BrowserBookmarksConnector()
            # Set chrome_bookmarks to nonexistent to avoid picking up real bookmarks
            connector.setup({
                "firefox_places": str(db_path),
                "chrome_bookmarks": "/nonexistent/Bookmarks",
            })
            docs = connector.fetch()

            assert len(docs) == 1
            assert docs[0].title == "Mozilla"
            assert docs[0].id.startswith("bookmark:firefox:")

    def test_no_bookmarks_found(self):
        from desksearch.plugins.builtin.browser_bookmarks import BrowserBookmarksConnector

        connector = BrowserBookmarksConnector()
        connector.setup({"chrome_bookmarks": "/nonexistent/path"})
        docs = connector.fetch()
        assert docs == []

    def test_nested_chrome_folders(self):
        from desksearch.plugins.builtin.browser_bookmarks import BrowserBookmarksConnector

        with tempfile.TemporaryDirectory() as d:
            bookmarks = {
                "roots": {
                    "bookmark_bar": {
                        "type": "folder",
                        "children": [
                            {
                                "type": "folder",
                                "name": "Subfolder",
                                "children": [
                                    {
                                        "type": "url",
                                        "name": "Nested",
                                        "url": "https://nested.example.com",
                                    }
                                ],
                            }
                        ],
                    }
                }
            }
            bk_path = Path(d) / "Bookmarks"
            bk_path.write_text(json.dumps(bookmarks))

            connector = BrowserBookmarksConnector()
            connector.setup({"chrome_bookmarks": str(bk_path)})
            docs = connector.fetch()
            assert len(docs) == 1
            assert docs[0].title == "Nested"


# ───────────────────────── Clipboard Monitor ─────────────────────────


class TestClipboardMonitor:
    """Test the clipboard monitor connector."""

    def test_fetch_with_text(self):
        from desksearch.plugins.builtin.clipboard_monitor import ClipboardMonitor

        with patch(
            "desksearch.plugins.builtin.clipboard_monitor._get_clipboard_text",
            return_value="Hello clipboard",
        ):
            monitor = ClipboardMonitor()
            monitor.setup()
            docs = monitor.fetch()
            assert len(docs) == 1
            assert docs[0].content == "Hello clipboard"
            assert docs[0].source == "clipboard"

    def test_fetch_deduplication(self):
        from desksearch.plugins.builtin.clipboard_monitor import ClipboardMonitor

        with patch(
            "desksearch.plugins.builtin.clipboard_monitor._get_clipboard_text",
            return_value="Same text",
        ):
            monitor = ClipboardMonitor()
            monitor.setup()
            docs1 = monitor.fetch()
            docs2 = monitor.fetch()  # Same text — should be deduplicated
            assert len(docs1) == 1
            assert len(docs2) == 0

    def test_fetch_empty_clipboard(self):
        from desksearch.plugins.builtin.clipboard_monitor import ClipboardMonitor

        with patch(
            "desksearch.plugins.builtin.clipboard_monitor._get_clipboard_text",
            return_value="",
        ):
            monitor = ClipboardMonitor()
            monitor.setup()
            docs = monitor.fetch()
            assert len(docs) == 0

    def test_fetch_none_clipboard(self):
        from desksearch.plugins.builtin.clipboard_monitor import ClipboardMonitor

        with patch(
            "desksearch.plugins.builtin.clipboard_monitor._get_clipboard_text",
            return_value=None,
        ):
            monitor = ClipboardMonitor()
            docs = monitor.fetch()
            assert len(docs) == 0

    def test_max_history_eviction(self):
        from desksearch.plugins.builtin.clipboard_monitor import ClipboardMonitor

        call_count = 0

        def _clipboard_gen():
            nonlocal call_count
            call_count += 1
            return f"Text {call_count}"

        with patch(
            "desksearch.plugins.builtin.clipboard_monitor._get_clipboard_text",
            side_effect=_clipboard_gen,
        ):
            monitor = ClipboardMonitor()
            monitor.setup({"max_history": 5})
            for _ in range(10):
                monitor.fetch()
            # Should have evicted oldest entries
            assert len(monitor._seen) <= 5


# ───────────────────────── Email Connector ─────────────────────────


class TestEmailConnector:
    """Test the email connector for .eml and .mbox files."""

    def _make_eml(self, directory: Path, filename: str = "test.eml") -> Path:
        """Create a sample .eml file."""
        msg = EmailMessage()
        msg["Subject"] = "Test Email Subject"
        msg["From"] = "sender@example.com"
        msg["To"] = "receiver@example.com"
        msg["Date"] = "Mon, 01 Jan 2025 12:00:00 +0000"
        msg.set_content("This is the body of the test email.")

        path = directory / filename
        path.write_bytes(msg.as_bytes())
        return path

    def _make_mbox(self, directory: Path, count: int = 3) -> Path:
        """Create a sample .mbox file."""
        path = directory / "test.mbox"
        mbox = mailbox.mbox(str(path))
        for i in range(count):
            msg = EmailMessage()
            msg["Subject"] = f"Mbox Email {i}"
            msg["From"] = f"user{i}@example.com"
            msg["Date"] = f"Mon, 0{i+1} Jan 2025 12:00:00 +0000"
            msg.set_content(f"Body of email {i}.")
            mbox.add(msg)
        mbox.flush()
        mbox.close()
        return path

    def test_eml_parsing(self):
        from desksearch.plugins.builtin.email_connector import EmailConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self._make_eml(d)

            connector = EmailConnector()
            connector.setup({"directories": [str(d)]})
            docs = connector.fetch()

            assert len(docs) == 1
            assert docs[0].title == "Test Email Subject"
            assert "sender@example.com" in docs[0].content
            assert "body of the test email" in docs[0].content

    def test_mbox_parsing(self):
        from desksearch.plugins.builtin.email_connector import EmailConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self._make_mbox(d, count=5)

            connector = EmailConnector()
            connector.setup({"directories": [str(d)]})
            docs = connector.fetch()

            assert len(docs) == 5
            assert all(d.id.startswith("email:") for d in docs)

    def test_no_directories(self):
        from desksearch.plugins.builtin.email_connector import EmailConnector

        connector = EmailConnector()
        connector.setup({})
        docs = connector.fetch()
        assert docs == []

    def test_nonexistent_directory(self):
        from desksearch.plugins.builtin.email_connector import EmailConnector

        connector = EmailConnector()
        connector.setup({"directories": ["/nonexistent/email/dir"]})
        docs = connector.fetch()
        assert docs == []

    def test_mixed_eml_and_mbox(self):
        from desksearch.plugins.builtin.email_connector import EmailConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self._make_eml(d)
            self._make_mbox(d, count=2)

            connector = EmailConnector()
            connector.setup({"directories": [str(d)]})
            docs = connector.fetch()

            # 1 eml + 2 mbox = 3
            assert len(docs) == 3


# ───────────────────────── Local Files Connector ─────────────────────────


class TestLocalFilesConnector:
    """Test the local files connector."""

    def test_basic_fetch(self):
        from desksearch.plugins.builtin.local_files import LocalFilesConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "hello.txt").write_text("Hello world")
            (d / "code.py").write_text("print('hi')")
            (d / "image.png").write_bytes(b"\x89PNG")  # not in default extensions

            connector = LocalFilesConnector()
            connector.setup({"directories": [str(d)]})
            docs = connector.fetch()

            names = {doc.title for doc in docs}
            assert "hello.txt" in names
            assert "code.py" in names
            assert "image.png" not in names  # .png not in default extensions

    def test_custom_extensions(self):
        from desksearch.plugins.builtin.local_files import LocalFilesConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "file.xyz").write_text("custom")
            (d / "file.txt").write_text("text")

            connector = LocalFilesConnector()
            connector.setup({
                "directories": [str(d)],
                "extensions": [".xyz"],
            })
            docs = connector.fetch()

            assert len(docs) == 1
            assert docs[0].title == "file.xyz"

    def test_excluded_dirs(self):
        from desksearch.plugins.builtin.local_files import LocalFilesConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "file.txt").write_text("root file")
            excluded = d / "node_modules"
            excluded.mkdir()
            (excluded / "lib.txt").write_text("should be excluded")

            connector = LocalFilesConnector()
            connector.setup({"directories": [str(d)]})
            docs = connector.fetch()

            assert len(docs) == 1
            assert docs[0].title == "file.txt"

    def test_max_file_size(self):
        from desksearch.plugins.builtin.local_files import LocalFilesConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "small.txt").write_text("small")
            (d / "big.txt").write_text("x" * 2_000_000)  # 2MB

            connector = LocalFilesConnector()
            connector.setup({
                "directories": [str(d)],
                "max_file_size_mb": 1,
            })
            docs = connector.fetch()

            assert len(docs) == 1
            assert docs[0].title == "small.txt"

    def test_empty_files_skipped(self):
        from desksearch.plugins.builtin.local_files import LocalFilesConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "empty.txt").write_text("")
            (d / "nonempty.txt").write_text("content")

            connector = LocalFilesConnector()
            connector.setup({"directories": [str(d)]})
            docs = connector.fetch()

            assert len(docs) == 1
            assert docs[0].title == "nonempty.txt"

    def test_nonexistent_directory(self):
        from desksearch.plugins.builtin.local_files import LocalFilesConnector

        connector = LocalFilesConnector()
        connector.setup({"directories": ["/nonexistent/dir"]})
        docs = connector.fetch()
        assert docs == []

    def test_document_metadata(self):
        from desksearch.plugins.builtin.local_files import LocalFilesConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "test.md").write_text("# Test")

            connector = LocalFilesConnector()
            connector.setup({"directories": [str(d)]})
            docs = connector.fetch()

            assert len(docs) == 1
            doc = docs[0]
            assert doc.id.startswith("localfile:")
            assert doc.metadata["extension"] == ".md"
            assert doc.metadata["size"] > 0
            assert "path" in doc.metadata


# ───────────────────────── Slack Export Connector ─────────────────────────


class TestSlackExportConnector:
    """Test the Slack workspace export connector."""

    def _make_export(self, base_dir: Path) -> Path:
        """Create a sample Slack export directory."""
        export = base_dir / "slack_export"
        export.mkdir()

        # users.json
        users = [
            {
                "id": "U001",
                "name": "alice",
                "real_name": "Alice Smith",
                "profile": {"display_name": "alice"},
            },
            {
                "id": "U002",
                "name": "bob",
                "real_name": "Bob Jones",
                "profile": {"display_name": "bob"},
            },
        ]
        (export / "users.json").write_text(json.dumps(users))

        # channels.json
        channels = [
            {"id": "C001", "name": "general"},
            {"id": "C002", "name": "random"},
        ]
        (export / "channels.json").write_text(json.dumps(channels))

        # #general messages
        general = export / "general"
        general.mkdir()
        (general / "2025-01-01.json").write_text(json.dumps([
            {"user": "U001", "text": "Hello everyone!", "ts": "1704067200.000000"},
            {"user": "U002", "text": "Hey Alice!", "ts": "1704067260.000000"},
        ]))
        (general / "2025-01-02.json").write_text(json.dumps([
            {"user": "U001", "text": "Let's discuss the project.", "ts": "1704153600.000000"},
        ]))

        # #random messages
        random_ch = export / "random"
        random_ch.mkdir()
        (random_ch / "2025-01-01.json").write_text(json.dumps([
            {"user": "U002", "text": "Check out this link", "ts": "1704067200.000000"},
            {"subtype": "bot_message", "text": "Bot message", "ts": "1704067300.000000"},
        ]))

        return export

    def test_basic_fetch(self):
        from desksearch.plugins.builtin.slack_export import SlackExportConnector

        with tempfile.TemporaryDirectory() as d:
            export = self._make_export(Path(d))

            connector = SlackExportConnector()
            connector.setup({"export_path": str(export)})
            docs = connector.fetch()

            # 2 days in general + 1 day in random = 3 docs
            assert len(docs) == 3
            assert all(d.id.startswith("slack:") for d in docs)

            # Check general channel day 1
            day1 = [d for d in docs if "general" in d.title and "2025-01-01" in d.title]
            assert len(day1) == 1
            assert "[alice]: Hello everyone!" in day1[0].content
            assert "[bob]: Hey Alice!" in day1[0].content

    def test_bot_messages_excluded_by_default(self):
        from desksearch.plugins.builtin.slack_export import SlackExportConnector

        with tempfile.TemporaryDirectory() as d:
            export = self._make_export(Path(d))

            connector = SlackExportConnector()
            connector.setup({"export_path": str(export)})
            docs = connector.fetch()

            random_docs = [doc for doc in docs if "random" in doc.title]
            assert len(random_docs) == 1
            assert "Bot message" not in random_docs[0].content

    def test_bot_messages_included_when_configured(self):
        from desksearch.plugins.builtin.slack_export import SlackExportConnector

        with tempfile.TemporaryDirectory() as d:
            export = self._make_export(Path(d))

            connector = SlackExportConnector()
            connector.setup({
                "export_path": str(export),
                "include_bots": True,
            })
            docs = connector.fetch()

            random_docs = [doc for doc in docs if "random" in doc.title]
            assert len(random_docs) == 1
            assert "Bot message" in random_docs[0].content

    def test_metadata(self):
        from desksearch.plugins.builtin.slack_export import SlackExportConnector

        with tempfile.TemporaryDirectory() as d:
            export = self._make_export(Path(d))

            connector = SlackExportConnector()
            connector.setup({"export_path": str(export)})
            docs = connector.fetch()

            for doc in docs:
                assert "channel" in doc.metadata
                assert "date" in doc.metadata
                assert "message_count" in doc.metadata
                assert doc.source.startswith("slack:#")

    def test_zip_export(self):
        """Test that ZIP archives are auto-extracted."""
        from desksearch.plugins.builtin.slack_export import SlackExportConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            export = self._make_export(d)

            # Create a ZIP from the export directory
            zip_path = d / "export.zip"
            shutil.make_archive(str(d / "export"), "zip", root_dir=str(export))

            # Remove the original directory
            shutil.rmtree(export)

            connector = SlackExportConnector()
            connector.setup({"export_path": str(zip_path)})
            docs = connector.fetch()
            assert len(docs) == 3

    def test_nonexistent_path(self):
        from desksearch.plugins.builtin.slack_export import SlackExportConnector

        connector = SlackExportConnector()
        connector.setup({"export_path": "/nonexistent/export"})
        docs = connector.fetch()
        assert docs == []

    def test_no_config(self):
        from desksearch.plugins.builtin.slack_export import SlackExportConnector

        connector = SlackExportConnector()
        connector.setup({})
        docs = connector.fetch()
        assert docs == []

    def test_empty_channel(self):
        from desksearch.plugins.builtin.slack_export import SlackExportConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            export = d / "export"
            export.mkdir()
            (export / "users.json").write_text("[]")
            empty_channel = export / "empty-channel"
            empty_channel.mkdir()
            (empty_channel / "2025-01-01.json").write_text("[]")

            connector = SlackExportConnector()
            connector.setup({"export_path": str(export)})
            docs = connector.fetch()
            assert docs == []


# ───────────────────────── Builtin Registration ─────────────────────────


class TestBuiltinRegistration:
    """Test that all built-in connectors are properly registered."""

    def test_all_builtin_connectors_list(self):
        from desksearch.plugins.builtin import ALL_BUILTIN_CONNECTORS

        names = [cls().name for cls in ALL_BUILTIN_CONNECTORS]
        assert "browser-bookmarks" in names
        assert "clipboard-monitor" in names
        assert "email-connector" in names
        assert "local-files" in names
        assert "slack-export" in names
        assert len(names) == 5

    def test_all_builtin_connectors_are_base_connector(self):
        from desksearch.plugins.builtin import ALL_BUILTIN_CONNECTORS

        for cls in ALL_BUILTIN_CONNECTORS:
            assert issubclass(cls, BaseConnectorPlugin)

    def test_all_builtin_connectors_instantiate(self):
        from desksearch.plugins.builtin import ALL_BUILTIN_CONNECTORS

        for cls in ALL_BUILTIN_CONNECTORS:
            instance = cls()
            assert instance.name
            assert instance.version
            assert instance.description

    def test_all_builtin_connectors_register(self):
        from desksearch.plugins.builtin import ALL_BUILTIN_CONNECTORS

        reg = PluginRegistry()
        for cls in ALL_BUILTIN_CONNECTORS:
            instance = cls()
            reg.register(instance)

        assert len(reg.connectors) == 5


# ───────────────────────── Connector API Endpoints ─────────────────────────


class TestConnectorAPI:
    """Test the /api/connectors endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client with the API app."""
        from fastapi.testclient import TestClient
        from desksearch.api.routes import router, set_config
        from desksearch.config import Config
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)

        with tempfile.TemporaryDirectory() as d:
            config = Config(data_dir=Path(d))
            set_config(config)
            yield TestClient(app)

    def test_list_connectors(self, client):
        resp = client.get("/api/connectors")
        assert resp.status_code == 200
        data = resp.json()
        assert "connectors" in data
        assert data["total"] == 5
        names = [c["name"] for c in data["connectors"]]
        assert "browser-bookmarks" in names
        assert "local-files" in names
        assert "slack-export" in names

    def test_connector_has_expected_fields(self, client):
        resp = client.get("/api/connectors")
        data = resp.json()
        for conn in data["connectors"]:
            assert "name" in conn
            assert "description" in conn
            assert "version" in conn
            assert "enabled" in conn
            assert "configured" in conn

    def test_update_connector_config(self, client):
        resp = client.put(
            "/api/connectors/email-connector/config",
            json={"config": {"directories": ["/tmp/emails"]}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["connector"] == "email-connector"
        assert data["config"]["directories"] == ["/tmp/emails"]

    def test_update_unknown_connector(self, client):
        resp = client.put(
            "/api/connectors/nonexistent/config",
            json={"config": {}},
        )
        assert resp.status_code == 404

    def test_sync_unknown_connector(self, client):
        resp = client.post("/api/connectors/nonexistent/sync")
        # Returns 503 (no pipeline) or 404 (unknown connector)
        assert resp.status_code in (404, 503)
