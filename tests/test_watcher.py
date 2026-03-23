"""Tests for the file watcher with debouncing."""
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from desksearch.config import Config
from desksearch.indexer.watcher import FileWatcher, IndexEventHandler, DEBOUNCE_SECONDS


@pytest.fixture
def config(tmp_path):
    """Create a minimal config for testing."""
    watch_dir = tmp_path / "watched"
    watch_dir.mkdir()
    return Config(
        data_dir=tmp_path / "data",
        index_paths=[watch_dir],
        file_extensions=[".txt", ".md", ".py"],
        excluded_dirs=[".git", "node_modules", "__pycache__"],
    )


@pytest.fixture
def callbacks():
    """Create mock callbacks."""
    return {
        "on_created": MagicMock(),
        "on_modified": MagicMock(),
        "on_deleted": MagicMock(),
    }


@pytest.fixture
def handler(config, callbacks):
    """Create an IndexEventHandler with mock callbacks."""
    return IndexEventHandler(
        config,
        on_created_cb=callbacks["on_created"],
        on_modified_cb=callbacks["on_modified"],
        on_deleted_cb=callbacks["on_deleted"],
    )


class _FakeEvent:
    """Minimal fake watchdog event."""
    def __init__(self, src_path, is_directory=False, dest_path=None):
        self.src_path = str(src_path)
        self.dest_path = str(dest_path) if dest_path else None
        self.is_directory = is_directory


class TestDebouncing:
    """Test that multiple events collapse into one via debouncing."""

    def test_multiple_modify_events_debounce_to_one(self, handler, callbacks):
        """Multiple modify events for the same file should result in one callback."""
        path = Path("/fake/dir/test.txt")

        # Fire 5 modify events rapidly
        for _ in range(5):
            handler.on_modified(_FakeEvent(path))

        # Callback should NOT have been called yet (debouncing)
        assert callbacks["on_modified"].call_count == 0

        # Wait for debounce to flush
        time.sleep(DEBOUNCE_SECONDS + 0.5)

        # Should have been called exactly once
        assert callbacks["on_modified"].call_count == 1
        callbacks["on_modified"].assert_called_once_with(path)

    def test_events_for_different_files_batch_together(self, handler, callbacks):
        """Events for different files within debounce window batch into one flush."""
        path1 = Path("/fake/dir/file1.txt")
        path2 = Path("/fake/dir/file2.txt")
        path3 = Path("/fake/dir/file3.md")

        handler.on_created(_FakeEvent(path1))
        handler.on_created(_FakeEvent(path2))
        handler.on_modified(_FakeEvent(path3))

        # Nothing yet
        assert callbacks["on_created"].call_count == 0
        assert callbacks["on_modified"].call_count == 0

        # Wait for flush
        time.sleep(DEBOUNCE_SECONDS + 0.5)

        assert callbacks["on_created"].call_count == 2
        assert callbacks["on_modified"].call_count == 1

    def test_last_event_type_wins_for_same_file(self, handler, callbacks):
        """If a file is created then modified, only modified callback fires."""
        path = Path("/fake/dir/test.txt")

        handler.on_created(_FakeEvent(path))
        handler.on_modified(_FakeEvent(path))

        time.sleep(DEBOUNCE_SECONDS + 0.5)

        # Last event was "modified", so only on_modified should fire
        assert callbacks["on_created"].call_count == 0
        assert callbacks["on_modified"].call_count == 1


class TestFileCreateTriggersCallback:
    """Test that file creation triggers the on_created callback."""

    def test_created_event(self, handler, callbacks):
        path = Path("/fake/dir/new_file.txt")
        handler.on_created(_FakeEvent(path))

        time.sleep(DEBOUNCE_SECONDS + 0.5)

        callbacks["on_created"].assert_called_once_with(path)
        assert handler.events_processed == 1


class TestFileDeleteTriggersCallback:
    """Test that file deletion triggers the on_deleted callback."""

    def test_deleted_event(self, handler, callbacks):
        path = Path("/fake/dir/removed.txt")
        handler.on_deleted(_FakeEvent(path))

        time.sleep(DEBOUNCE_SECONDS + 0.5)

        callbacks["on_deleted"].assert_called_once_with(path)
        assert handler.events_processed == 1


class TestExcludedDirs:
    """Test that events in excluded directories are ignored."""

    def test_git_dir_ignored(self, handler, callbacks):
        path = Path("/fake/dir/.git/objects/abc123")
        handler.on_created(_FakeEvent(path))
        handler.on_modified(_FakeEvent(path))

        time.sleep(DEBOUNCE_SECONDS + 0.5)

        callbacks["on_created"].assert_not_called()
        callbacks["on_modified"].assert_not_called()

    def test_node_modules_ignored(self, handler, callbacks):
        path = Path("/fake/dir/node_modules/pkg/index.txt")
        handler.on_modified(_FakeEvent(path))

        time.sleep(DEBOUNCE_SECONDS + 0.5)

        callbacks["on_modified"].assert_not_called()

    def test_pycache_ignored(self, handler, callbacks):
        path = Path("/fake/dir/__pycache__/module.txt")
        handler.on_modified(_FakeEvent(path))

        time.sleep(DEBOUNCE_SECONDS + 0.5)

        callbacks["on_modified"].assert_not_called()


class TestNonMatchingExtensions:
    """Test that files with non-matching extensions are ignored."""

    def test_jpg_ignored(self, handler, callbacks):
        path = Path("/fake/dir/photo.jpg")
        handler.on_created(_FakeEvent(path))

        time.sleep(DEBOUNCE_SECONDS + 0.5)

        callbacks["on_created"].assert_not_called()

    def test_exe_ignored(self, handler, callbacks):
        path = Path("/fake/dir/program.exe")
        handler.on_modified(_FakeEvent(path))

        time.sleep(DEBOUNCE_SECONDS + 0.5)

        callbacks["on_modified"].assert_not_called()

    def test_matching_extension_passes(self, handler, callbacks):
        path = Path("/fake/dir/script.py")
        handler.on_created(_FakeEvent(path))

        time.sleep(DEBOUNCE_SECONDS + 0.5)

        callbacks["on_created"].assert_called_once_with(path)


class TestDirectoryEventsIgnored:
    """Test that directory events are ignored."""

    def test_directory_created_ignored(self, handler, callbacks):
        handler.on_created(_FakeEvent("/fake/dir/subdir", is_directory=True))

        time.sleep(DEBOUNCE_SECONDS + 0.5)

        callbacks["on_created"].assert_not_called()

    def test_directory_deleted_ignored(self, handler, callbacks):
        handler.on_deleted(_FakeEvent("/fake/dir/subdir", is_directory=True))

        time.sleep(DEBOUNCE_SECONDS + 0.5)

        callbacks["on_deleted"].assert_not_called()


class TestMoveEvent:
    """Test rename/move handling (delete old + create new)."""

    def test_move_triggers_delete_and_create(self, handler, callbacks):
        old_path = Path("/fake/dir/old_name.txt")
        new_path = Path("/fake/dir/new_name.txt")

        handler.on_moved(_FakeEvent(old_path, dest_path=new_path))

        time.sleep(DEBOUNCE_SECONDS + 0.5)

        callbacks["on_deleted"].assert_called_once_with(old_path)
        callbacks["on_created"].assert_called_once_with(new_path)


class TestFileWatcher:
    """Test the FileWatcher class."""

    def test_watcher_properties(self, config, callbacks):
        watcher = FileWatcher(
            config,
            on_created=callbacks["on_created"],
            on_modified=callbacks["on_modified"],
            on_deleted=callbacks["on_deleted"],
        )
        assert watcher.is_running is False
        assert watcher.watched_paths == []
        assert watcher.events_processed == 0

    def test_watcher_start_stop(self, config, callbacks):
        watcher = FileWatcher(
            config,
            on_created=callbacks["on_created"],
            on_modified=callbacks["on_modified"],
            on_deleted=callbacks["on_deleted"],
        )
        watcher.start()
        assert watcher.is_running is True
        assert len(watcher.watched_paths) > 0

        watcher.stop()
        assert watcher.is_running is False

    def test_events_processed_counter(self, handler, callbacks):
        """Events processed counter increments after flush."""
        handler.on_created(_FakeEvent(Path("/fake/dir/a.txt")))
        handler.on_modified(_FakeEvent(Path("/fake/dir/b.txt")))

        time.sleep(DEBOUNCE_SECONDS + 0.5)

        assert handler.events_processed == 2
