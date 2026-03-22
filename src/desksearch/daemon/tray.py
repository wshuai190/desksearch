"""System tray integration for DeskSearch using pystray.

Provides a tray icon with menu for controlling the daemon from the desktop.
Works on macOS, Linux (with AppIndicator), and Windows.
"""
import logging
import threading
import webbrowser
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _create_icon_image():
    """Create a simple search-magnifier icon as a PIL Image."""
    from PIL import Image, ImageDraw

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw magnifying glass circle
    cx, cy, r = 24, 24, 16
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        outline=(59, 130, 246, 255),  # blue
        width=4,
    )
    # Draw handle
    draw.line(
        [cx + r - 3, cy + r - 3, size - 6, size - 6],
        fill=(59, 130, 246, 255),
        width=4,
    )
    return img


class SystemTray:
    """System tray icon and menu for DeskSearch."""

    def __init__(self, service) -> None:
        """
        Args:
            service: BackgroundService instance to control.
        """
        self._service = service
        self._icon = None
        self._paused = False

    def _open_search(self, icon=None, item=None) -> None:
        cfg = self._service.config
        webbrowser.open(f"http://{cfg.host}:{cfg.port}")

    def _reindex(self, icon=None, item=None) -> None:
        """Queue a full reindex of all configured paths."""
        logger.info("Reindex triggered from tray")
        if self._service._pipeline is None:
            return
        def _do_reindex():
            for path in self._service.config.index_paths:
                if path.exists() and path.is_dir():
                    try:
                        gen = self._service._pipeline.index_directory(path)
                        try:
                            while True:
                                next(gen)
                        except StopIteration:
                            pass
                    except Exception:
                        logger.exception("Error reindexing %s", path)
            logger.info("Reindex complete")
            self._update_tooltip()

        threading.Thread(target=_do_reindex, daemon=True, name="reindex").start()

    def _toggle_pause(self, icon=None, item=None) -> None:
        self._paused = not self._paused
        self._service._indexing_paused = self._paused
        state = "paused" if self._paused else "resumed"
        logger.info("Indexing %s from tray", state)
        self._update_tooltip()

    def _quit(self, icon=None, item=None) -> None:
        logger.info("Quit requested from tray")
        self._service.stop()
        if self._icon:
            self._icon.stop()

    def _get_pause_text(self, item=None) -> str:
        return "Resume Indexing" if self._paused else "Pause Indexing"

    def _update_tooltip(self) -> None:
        if self._icon is None:
            return
        doc_count = 0
        if self._service._store:
            try:
                doc_count = self._service._store.document_count()
            except Exception:
                pass
        status = "Paused" if self._paused else "Running"
        self._icon.title = f"DeskSearch — {status} ({doc_count} files)"

    def run(self) -> None:
        """Start the system tray icon. Blocks until stopped."""
        try:
            import pystray
            from pystray import MenuItem as Item
        except ImportError:
            logger.warning(
                "pystray not installed — system tray disabled. "
                "Install with: pip install desksearch[desktop]"
            )
            return

        try:
            image = _create_icon_image()
        except ImportError:
            logger.warning("Pillow not installed — system tray disabled.")
            return

        menu = pystray.Menu(
            Item("Open Search", self._open_search, default=True),
            pystray.Menu.SEPARATOR,
            Item("Reindex All", self._reindex),
            Item(self._get_pause_text, self._toggle_pause),
            pystray.Menu.SEPARATOR,
            Item("Quit DeskSearch", self._quit),
        )

        self._icon = pystray.Icon(
            "desksearch",
            image,
            "DeskSearch",
            menu,
        )

        self._update_tooltip()
        logger.info("System tray icon started")
        self._icon.run()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()
