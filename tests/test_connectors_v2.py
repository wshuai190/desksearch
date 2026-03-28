"""Tests for the v2 connector system (desksearch.connectors).

Covers:
  - Connector ABC and state tracking
  - ConnectorRegistry (register, discover, enable/disable, sync)
  - Built-in connectors:
    * LocalFilesConnector
    * EmailMboxConnector
    * ChromeBookmarksConnector
    * SlackExportConnector
  - Connector API endpoints (/api/connectors/v2/...)

Uses fixture data only — never touches real user data.
"""

from __future__ import annotations

import json
import mailbox
import tempfile
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Iterator, Optional

import pytest

from desksearch.connectors.base import Connector
from desksearch.plugins.base import Document


# ═══════════════════════════ Connector ABC ═══════════════════════════


class _DummyConnector(Connector):
    """Minimal concrete connector for testing the ABC."""

    @property
    def name(self) -> str:
        return "dummy"

    @property
    def description(self) -> str:
        return "A test connector"

    def configure(self, config: dict[str, Any]) -> None:
        self._config = config

    def fetch(self) -> Iterator[Document]:
        yield Document(id="d:1", title="Doc 1", content="Hello")
        yield Document(id="d:2", title="Doc 2", content="World")


class TestConnectorABC:
    """Test the Connector abstract base class."""

    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            Connector()  # type: ignore

    def test_concrete_connector(self):
        c = _DummyConnector()
        assert c.name == "dummy"
        assert c.description == "A test connector"

    def test_default_status(self):
        c = _DummyConnector()
        status = c.status()
        assert status["enabled"] is False
        assert status["last_sync"] is None
        assert status["doc_count"] == 0
        assert status["errors"] == []
        assert status["schedule"] is None

    def test_enable_disable(self):
        c = _DummyConnector()
        assert c.enabled is False
        c.enabled = True
        assert c.enabled is True
        assert c.status()["enabled"] is True

    def test_record_sync(self):
        c = _DummyConnector()
        c.record_sync(42, errors=["one error"])
        status = c.status()
        assert status["doc_count"] == 42
        assert status["errors"] == ["one error"]
        assert status["last_sync"] is not None

    def test_fetch_is_iterator(self):
        c = _DummyConnector()
        result = c.fetch()
        # Should be an iterator, not a list
        assert hasattr(result, "__next__")
        docs = list(result)
        assert len(docs) == 2

    def test_schedule_default_none(self):
        c = _DummyConnector()
        assert c.schedule() is None

    def test_validate_config_default_empty(self):
        c = _DummyConnector()
        assert c.validate_config({"anything": True}) == []

    def test_repr(self):
        c = _DummyConnector()
        assert "dummy" in repr(c)
        assert "disabled" in repr(c)
        c.enabled = True
        assert "enabled" in repr(c)

    def test_configure_stores_config(self):
        c = _DummyConnector()
        c.configure({"key": "value"})
        assert c._config == {"key": "value"}


# ═══════════════════════════ ConnectorRegistry ═══════════════════════════


class TestConnectorRegistry:
    """Test the ConnectorRegistry."""

    def test_register_and_get(self):
        from desksearch.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        c = _DummyConnector()
        reg.register(c)
        assert reg.get("dummy") is c
        assert reg.get("nonexistent") is None

    def test_unregister(self):
        from desksearch.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        reg.register(_DummyConnector())
        assert reg.unregister("dummy") is True
        assert reg.unregister("dummy") is False
        assert reg.get("dummy") is None

    def test_discover(self):
        from desksearch.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        reg.discover()
        assert len(reg) == 4
        assert reg.get("local-files") is not None
        assert reg.get("email-mbox") is not None
        assert reg.get("chrome-bookmarks") is not None
        assert reg.get("slack-export") is not None

    def test_all(self):
        from desksearch.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        reg.register(_DummyConnector())
        all_connectors = reg.all()
        assert "dummy" in all_connectors
        # Returns a copy, not the internal dict
        all_connectors["dummy"] = None  # type: ignore
        assert reg.get("dummy") is not None

    def test_list_status(self):
        from desksearch.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        reg.register(_DummyConnector())
        statuses = reg.list_status()
        assert len(statuses) == 1
        assert statuses[0]["name"] == "dummy"
        assert statuses[0]["description"] == "A test connector"

    def test_enable_disable(self):
        from desksearch.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        reg.register(_DummyConnector())
        assert reg.enable("dummy") is True
        assert reg.get("dummy").enabled is True
        assert reg.disable("dummy") is True
        assert reg.get("dummy").enabled is False
        assert reg.enable("nonexistent") is False

    def test_configure(self):
        from desksearch.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        reg.register(_DummyConnector())
        errors = reg.configure("dummy", {"key": "val"})
        assert errors == []
        assert reg.get("dummy")._config == {"key": "val"}

    def test_configure_unknown(self):
        from desksearch.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        errors = reg.configure("nonexistent", {})
        assert len(errors) == 1

    def test_sync(self):
        from desksearch.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        reg.register(_DummyConnector())
        docs, errors = reg.sync("dummy")
        assert len(docs) == 2
        assert errors == []
        # Check state was recorded
        status = reg.get("dummy").status()
        assert status["doc_count"] == 2
        assert status["last_sync"] is not None

    def test_sync_unknown(self):
        from desksearch.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        docs, errors = reg.sync("nonexistent")
        assert docs == []
        assert len(errors) == 1

    def test_sync_all_enabled(self):
        from desksearch.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        c1 = _DummyConnector()
        c1.enabled = True
        reg.register(c1)

        # A second connector (disabled)
        class Other(Connector):
            @property
            def name(self): return "other"
            @property
            def description(self): return "other"
            def configure(self, config): pass
            def fetch(self):
                yield Document(id="o:1", title="O", content="C")

        o = Other()
        o.enabled = False
        reg.register(o)

        results = reg.sync_all_enabled()
        assert "dummy" in results
        assert "other" not in results

    def test_len_and_repr(self):
        from desksearch.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        assert len(reg) == 0
        reg.register(_DummyConnector())
        assert len(reg) == 1
        assert "total=1" in repr(reg)


# ═══════════════════════════ LocalFilesConnector ═══════════════════════════


class TestLocalFilesConnector:
    """Test the local files connector."""

    def test_basic_fetch(self):
        from desksearch.connectors.local_files import LocalFilesConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "hello.txt").write_text("Hello world")
            (d / "code.py").write_text("print('hi')")
            (d / "image.png").write_bytes(b"\x89PNG")

            c = LocalFilesConnector()
            c.configure({"directories": [str(d)]})
            docs = list(c.fetch())

            names = {doc.title for doc in docs}
            assert "hello.txt" in names
            assert "code.py" in names
            assert "image.png" not in names  # not in default extensions

    def test_custom_extensions(self):
        from desksearch.connectors.local_files import LocalFilesConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "file.xyz").write_text("custom")
            (d / "file.txt").write_text("text")

            c = LocalFilesConnector()
            c.configure({"directories": [str(d)], "extensions": [".xyz"]})
            docs = list(c.fetch())
            assert len(docs) == 1
            assert docs[0].title == "file.xyz"

    def test_excluded_dirs(self):
        from desksearch.connectors.local_files import LocalFilesConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "file.txt").write_text("root file")
            excluded = d / "node_modules"
            excluded.mkdir()
            (excluded / "lib.txt").write_text("excluded")

            c = LocalFilesConnector()
            c.configure({"directories": [str(d)]})
            docs = list(c.fetch())
            assert len(docs) == 1

    def test_max_file_size(self):
        from desksearch.connectors.local_files import LocalFilesConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "small.txt").write_text("small")
            (d / "big.txt").write_text("x" * 2_000_000)

            c = LocalFilesConnector()
            c.configure({"directories": [str(d)], "max_file_size_mb": 1})
            docs = list(c.fetch())
            assert len(docs) == 1
            assert docs[0].title == "small.txt"

    def test_empty_files_skipped(self):
        from desksearch.connectors.local_files import LocalFilesConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "empty.txt").write_text("")
            (d / "content.txt").write_text("content")

            c = LocalFilesConnector()
            c.configure({"directories": [str(d)]})
            docs = list(c.fetch())
            assert len(docs) == 1

    def test_nonexistent_directory(self):
        from desksearch.connectors.local_files import LocalFilesConnector

        c = LocalFilesConnector()
        c.configure({"directories": ["/nonexistent/dir"]})
        docs = list(c.fetch())
        assert docs == []

    def test_document_metadata(self):
        from desksearch.connectors.local_files import LocalFilesConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "test.md").write_text("# Test")

            c = LocalFilesConnector()
            c.configure({"directories": [str(d)]})
            docs = list(c.fetch())
            assert len(docs) == 1
            assert docs[0].id.startswith("localfile:")
            assert docs[0].metadata["extension"] == ".md"
            assert docs[0].metadata["size"] > 0

    def test_schedule_with_dirs(self):
        from desksearch.connectors.local_files import LocalFilesConnector

        c = LocalFilesConnector()
        assert c.schedule() is None
        c.configure({"directories": ["/tmp"]})
        assert c.schedule() is not None

    def test_validate_config(self):
        from desksearch.connectors.local_files import LocalFilesConnector

        c = LocalFilesConnector()
        errors = c.validate_config({"directories": ["/nonexistent/path"]})
        assert len(errors) == 1

    def test_returns_iterator(self):
        from desksearch.connectors.local_files import LocalFilesConnector

        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.txt").write_text("a")
            c = LocalFilesConnector()
            c.configure({"directories": [str(d)]})
            result = c.fetch()
            assert hasattr(result, "__next__")


# ═══════════════════════════ EmailMboxConnector ═══════════════════════════


class TestEmailMboxConnector:
    """Test the email/mbox connector."""

    def _make_eml(self, directory: Path, filename: str = "test.eml") -> Path:
        msg = EmailMessage()
        msg["Subject"] = "Test Subject"
        msg["From"] = "sender@example.com"
        msg["To"] = "receiver@example.com"
        msg["Date"] = "Mon, 01 Jan 2025 12:00:00 +0000"
        msg.set_content("This is the email body.")
        path = directory / filename
        path.write_bytes(msg.as_bytes())
        return path

    def _make_mbox(self, directory: Path, count: int = 3) -> Path:
        path = directory / "test.mbox"
        mbox = mailbox.mbox(str(path))
        for i in range(count):
            msg = EmailMessage()
            msg["Subject"] = f"Email {i}"
            msg["From"] = f"user{i}@example.com"
            msg["To"] = "me@example.com"
            msg["Date"] = f"Mon, 0{i+1} Jan 2025 12:00:00 +0000"
            msg.set_content(f"Body of email {i}.")
            mbox.add(msg)
        mbox.flush()
        mbox.close()
        return path

    def test_eml_parsing(self):
        from desksearch.connectors.email_mbox import EmailMboxConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self._make_eml(d)
            c = EmailMboxConnector()
            c.configure({"directories": [str(d)]})
            docs = list(c.fetch())
            assert len(docs) == 1
            assert docs[0].title == "Test Subject"
            assert "sender@example.com" in docs[0].content
            assert "email body" in docs[0].content

    def test_eml_metadata(self):
        from desksearch.connectors.email_mbox import EmailMboxConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self._make_eml(d)
            c = EmailMboxConnector()
            c.configure({"directories": [str(d)]})
            docs = list(c.fetch())
            assert docs[0].metadata["from"] == "sender@example.com"
            assert docs[0].metadata["to"] == "receiver@example.com"
            assert docs[0].metadata["subject"] == "Test Subject"
            assert "date" in docs[0].metadata

    def test_mbox_parsing(self):
        from desksearch.connectors.email_mbox import EmailMboxConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self._make_mbox(d, count=5)
            c = EmailMboxConnector()
            c.configure({"directories": [str(d)]})
            docs = list(c.fetch())
            assert len(docs) == 5
            assert all(doc.id.startswith("email:") for doc in docs)

    def test_mixed_eml_and_mbox(self):
        from desksearch.connectors.email_mbox import EmailMboxConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self._make_eml(d)
            self._make_mbox(d, count=2)
            c = EmailMboxConnector()
            c.configure({"directories": [str(d)]})
            docs = list(c.fetch())
            assert len(docs) == 3

    def test_no_directories(self):
        from desksearch.connectors.email_mbox import EmailMboxConnector

        c = EmailMboxConnector()
        c.configure({})
        docs = list(c.fetch())
        assert docs == []

    def test_nonexistent_directory(self):
        from desksearch.connectors.email_mbox import EmailMboxConnector

        c = EmailMboxConnector()
        c.configure({"directories": ["/nonexistent/email"]})
        docs = list(c.fetch())
        assert docs == []

    def test_schedule_with_dirs(self):
        from desksearch.connectors.email_mbox import EmailMboxConnector

        c = EmailMboxConnector()
        assert c.schedule() is None
        c.configure({"directories": ["/tmp"]})
        assert c.schedule() is not None

    def test_returns_iterator(self):
        from desksearch.connectors.email_mbox import EmailMboxConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self._make_eml(d)
            c = EmailMboxConnector()
            c.configure({"directories": [str(d)]})
            result = c.fetch()
            assert hasattr(result, "__next__")


# ═══════════════════════════ ChromeBookmarksConnector ═══════════════════════════


class TestChromeBookmarksConnector:
    """Test the Chrome bookmarks connector."""

    def _make_bookmarks(self, directory: Path) -> Path:
        bookmarks = {
            "roots": {
                "bookmark_bar": {
                    "type": "folder",
                    "name": "Bookmarks Bar",
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
                        {
                            "type": "folder",
                            "name": "Research",
                            "children": [
                                {
                                    "type": "url",
                                    "name": "ArXiv",
                                    "url": "https://arxiv.org",
                                }
                            ],
                        },
                    ],
                },
                "other": {
                    "type": "folder",
                    "name": "Other Bookmarks",
                    "children": [],
                },
            }
        }
        path = directory / "Bookmarks"
        path.write_text(json.dumps(bookmarks))
        return path

    def test_basic_fetch(self):
        from desksearch.connectors.chrome_bookmarks import ChromeBookmarksConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            bk = self._make_bookmarks(d)
            c = ChromeBookmarksConnector()
            c.configure({"bookmarks_path": str(bk)})
            docs = list(c.fetch())
            assert len(docs) == 3
            assert all(doc.id.startswith("bookmark:chrome:") for doc in docs)

    def test_titles_and_urls(self):
        from desksearch.connectors.chrome_bookmarks import ChromeBookmarksConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            bk = self._make_bookmarks(d)
            c = ChromeBookmarksConnector()
            c.configure({"bookmarks_path": str(bk)})
            docs = list(c.fetch())
            titles = {doc.title for doc in docs}
            assert "Example" in titles
            assert "ArXiv" in titles
            urls = [doc.metadata["url"] for doc in docs]
            assert "https://example.com" in urls
            assert "https://arxiv.org" in urls

    def test_folder_metadata(self):
        from desksearch.connectors.chrome_bookmarks import ChromeBookmarksConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            bk = self._make_bookmarks(d)
            c = ChromeBookmarksConnector()
            c.configure({"bookmarks_path": str(bk)})
            docs = list(c.fetch())
            arxiv_doc = [doc for doc in docs if doc.title == "ArXiv"][0]
            assert "Research" in arxiv_doc.metadata["folder"]

    def test_nonexistent_path(self):
        from desksearch.connectors.chrome_bookmarks import ChromeBookmarksConnector

        c = ChromeBookmarksConnector()
        c.configure({"bookmarks_path": "/nonexistent/Bookmarks"})
        docs = list(c.fetch())
        assert docs == []

    def test_no_config_no_file(self):
        from desksearch.connectors.chrome_bookmarks import ChromeBookmarksConnector

        c = ChromeBookmarksConnector()
        c.configure({})
        # May or may not find default Chrome bookmarks; either way should not crash
        docs = list(c.fetch())
        assert isinstance(docs, list)

    def test_schedule(self):
        from desksearch.connectors.chrome_bookmarks import ChromeBookmarksConnector

        c = ChromeBookmarksConnector()
        assert c.schedule() == "0 3 * * *"

    def test_validate_config_missing_file(self):
        from desksearch.connectors.chrome_bookmarks import ChromeBookmarksConnector

        c = ChromeBookmarksConnector()
        errors = c.validate_config({"bookmarks_path": "/nonexistent/file"})
        assert len(errors) == 1

    def test_returns_iterator(self):
        from desksearch.connectors.chrome_bookmarks import ChromeBookmarksConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            bk = self._make_bookmarks(d)
            c = ChromeBookmarksConnector()
            c.configure({"bookmarks_path": str(bk)})
            result = c.fetch()
            assert hasattr(result, "__next__")


# ═══════════════════════════ SlackExportConnector ═══════════════════════════


class TestSlackExportConnector:
    """Test the Slack export connector."""

    def _make_export(self, base_dir: Path) -> Path:
        export = base_dir / "slack_export"
        export.mkdir()

        users = [
            {"id": "U001", "name": "alice", "profile": {"display_name": "alice"}},
            {"id": "U002", "name": "bob", "profile": {"display_name": "bob"}},
        ]
        (export / "users.json").write_text(json.dumps(users))

        channels = [
            {"id": "C001", "name": "general"},
            {"id": "C002", "name": "random"},
        ]
        (export / "channels.json").write_text(json.dumps(channels))

        general = export / "general"
        general.mkdir()
        (general / "2025-01-01.json").write_text(json.dumps([
            {"user": "U001", "text": "Hello everyone!", "ts": "1704067200.0"},
            {"user": "U002", "text": "Hey Alice!", "ts": "1704067260.0"},
        ]))
        (general / "2025-01-02.json").write_text(json.dumps([
            {"user": "U001", "text": "Project update.", "ts": "1704153600.0"},
        ]))

        random_ch = export / "random"
        random_ch.mkdir()
        (random_ch / "2025-01-01.json").write_text(json.dumps([
            {"user": "U002", "text": "Check this out", "ts": "1704067200.0"},
            {"subtype": "bot_message", "text": "Bot says hi", "ts": "1704067300.0"},
        ]))

        return export

    def test_basic_fetch(self):
        from desksearch.connectors.slack_export import SlackExportConnector

        with tempfile.TemporaryDirectory() as d:
            export = self._make_export(Path(d))
            c = SlackExportConnector()
            c.configure({"export_path": str(export)})
            docs = list(c.fetch())
            # 2 days in general + 1 day in random = 3
            assert len(docs) == 3
            assert all(doc.id.startswith("slack:") for doc in docs)

    def test_user_names_resolved(self):
        from desksearch.connectors.slack_export import SlackExportConnector

        with tempfile.TemporaryDirectory() as d:
            export = self._make_export(Path(d))
            c = SlackExportConnector()
            c.configure({"export_path": str(export)})
            docs = list(c.fetch())
            general_day1 = [doc for doc in docs if "general" in doc.title and "2025-01-01" in doc.title]
            assert len(general_day1) == 1
            assert "[alice]" in general_day1[0].content
            assert "[bob]" in general_day1[0].content

    def test_bot_messages_excluded_by_default(self):
        from desksearch.connectors.slack_export import SlackExportConnector

        with tempfile.TemporaryDirectory() as d:
            export = self._make_export(Path(d))
            c = SlackExportConnector()
            c.configure({"export_path": str(export)})
            docs = list(c.fetch())
            random_docs = [doc for doc in docs if "random" in doc.title]
            assert len(random_docs) == 1
            assert "Bot says hi" not in random_docs[0].content

    def test_bot_messages_included(self):
        from desksearch.connectors.slack_export import SlackExportConnector

        with tempfile.TemporaryDirectory() as d:
            export = self._make_export(Path(d))
            c = SlackExportConnector()
            c.configure({"export_path": str(export), "include_bots": True})
            docs = list(c.fetch())
            random_docs = [doc for doc in docs if "random" in doc.title]
            assert "Bot says hi" in random_docs[0].content

    def test_metadata(self):
        from desksearch.connectors.slack_export import SlackExportConnector

        with tempfile.TemporaryDirectory() as d:
            export = self._make_export(Path(d))
            c = SlackExportConnector()
            c.configure({"export_path": str(export)})
            docs = list(c.fetch())
            for doc in docs:
                assert "channel" in doc.metadata
                assert "date" in doc.metadata
                assert "message_count" in doc.metadata
                assert doc.source.startswith("slack:#")

    def test_zip_export(self):
        import shutil
        from desksearch.connectors.slack_export import SlackExportConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            export = self._make_export(d)
            zip_path = d / "export.zip"
            shutil.make_archive(str(d / "export"), "zip", root_dir=str(export))
            shutil.rmtree(export)

            c = SlackExportConnector()
            c.configure({"export_path": str(zip_path)})
            docs = list(c.fetch())
            assert len(docs) == 3

    def test_nonexistent_path(self):
        from desksearch.connectors.slack_export import SlackExportConnector

        c = SlackExportConnector()
        c.configure({"export_path": "/nonexistent/export"})
        docs = list(c.fetch())
        assert docs == []

    def test_no_config(self):
        from desksearch.connectors.slack_export import SlackExportConnector

        c = SlackExportConnector()
        c.configure({})
        docs = list(c.fetch())
        assert docs == []

    def test_empty_channel(self):
        from desksearch.connectors.slack_export import SlackExportConnector

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            export = d / "export"
            export.mkdir()
            (export / "users.json").write_text("[]")
            empty = export / "empty-channel"
            empty.mkdir()
            (empty / "2025-01-01.json").write_text("[]")

            c = SlackExportConnector()
            c.configure({"export_path": str(export)})
            docs = list(c.fetch())
            assert docs == []

    def test_schedule_is_none(self):
        from desksearch.connectors.slack_export import SlackExportConnector

        c = SlackExportConnector()
        assert c.schedule() is None

    def test_returns_iterator(self):
        from desksearch.connectors.slack_export import SlackExportConnector

        with tempfile.TemporaryDirectory() as d:
            export = self._make_export(Path(d))
            c = SlackExportConnector()
            c.configure({"export_path": str(export)})
            result = c.fetch()
            assert hasattr(result, "__next__")


# ═══════════════════════════ API Endpoints ═══════════════════════════


class TestConnectorAPI:
    """Test the /api/connectors/v2/ endpoints."""

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from desksearch.api.connectors import connector_router, set_connector_components
        from desksearch.connectors import ConnectorRegistry

        app = FastAPI()
        app.include_router(connector_router)

        reg = ConnectorRegistry()
        reg.discover()
        set_connector_components(reg)

        yield TestClient(app)

    def test_list_connectors(self, client):
        resp = client.get("/api/connectors/v2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 4
        names = [c["name"] for c in data["connectors"]]
        assert "local-files" in names
        assert "email-mbox" in names
        assert "chrome-bookmarks" in names
        assert "slack-export" in names

    def test_get_connector(self, client):
        resp = client.get("/api/connectors/v2/local-files")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "local-files"
        assert "enabled" in data
        assert "schedule" in data

    def test_get_unknown_connector(self, client):
        resp = client.get("/api/connectors/v2/nonexistent")
        assert resp.status_code == 404

    def test_enable_connector(self, client):
        resp = client.post("/api/connectors/v2/local-files/enable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

        # Verify
        resp = client.get("/api/connectors/v2/local-files")
        assert resp.json()["enabled"] is True

    def test_disable_connector(self, client):
        client.post("/api/connectors/v2/local-files/enable")
        resp = client.post("/api/connectors/v2/local-files/disable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_enable_unknown_connector(self, client):
        resp = client.post("/api/connectors/v2/nonexistent/enable")
        assert resp.status_code == 404

    def test_update_config(self, client):
        with tempfile.TemporaryDirectory() as d:
            resp = client.put(
                "/api/connectors/v2/email-mbox/config",
                json={"config": {"directories": [str(d)]}},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    def test_update_config_unknown(self, client):
        resp = client.put(
            "/api/connectors/v2/nonexistent/config",
            json={"config": {}},
        )
        assert resp.status_code == 400

    def test_sync_connector(self, client):
        # Sync with unconfigured connector — should return 0 docs
        resp = client.post("/api/connectors/v2/email-mbox/sync")
        assert resp.status_code == 200
        data = resp.json()
        assert data["documents_found"] == 0

    def test_sync_unknown_connector(self, client):
        resp = client.post("/api/connectors/v2/nonexistent/sync")
        assert resp.status_code == 404

    def test_sync_with_data(self, client):
        """Sync a connector that has actual fixture data."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "test.txt").write_text("Hello world")

            # Configure, then sync
            client.put(
                "/api/connectors/v2/local-files/config",
                json={"config": {"directories": [str(d)]}},
            )
            resp = client.post("/api/connectors/v2/local-files/sync")
            assert resp.status_code == 200
            assert resp.json()["documents_found"] == 1
