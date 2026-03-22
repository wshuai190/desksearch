"""Auto-start configuration for DeskSearch daemon.

Supports:
- macOS: LaunchAgent plist
- Linux: XDG autostart .desktop file or systemd user service
- Windows: Start Menu startup folder shortcut
"""
import logging
import os
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

MACOS_PLIST_NAME = "com.desksearch.daemon.plist"
LINUX_DESKTOP_NAME = "desksearch.desktop"
LINUX_SYSTEMD_NAME = "desksearch.service"


def _find_executable() -> str:
    """Find the desksearch executable path."""
    exe = shutil.which("desksearch")
    if exe:
        return exe
    # Fallback: use python -m desksearch
    return f"{sys.executable} -m desksearch"


# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------

def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / MACOS_PLIST_NAME


def _install_macos() -> Path:
    exe = _find_executable()
    # Split exe into program and args for ProgramArguments
    parts = exe.split() + ["daemon", "start", "--no-daemonize"]

    program_args = "\n".join(f"        <string>{p}</string>" for p in parts)

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.desksearch.daemon</string>
    <key>ProgramArguments</key>
    <array>
{program_args}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>{Path.home() / ".desksearch" / "desksearch.log"}</string>
    <key>StandardErrorPath</key>
    <string>{Path.home() / ".desksearch" / "desksearch.log"}</string>
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
"""
    path = _macos_plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plist_content)
    logger.info("Installed macOS LaunchAgent: %s", path)
    return path


def _uninstall_macos() -> bool:
    path = _macos_plist_path()
    if path.exists():
        # Unload first if loaded
        os.system(f"launchctl unload '{path}' 2>/dev/null")
        path.unlink()
        logger.info("Removed macOS LaunchAgent: %s", path)
        return True
    return False


# ---------------------------------------------------------------------------
# Linux
# ---------------------------------------------------------------------------

def _linux_desktop_path() -> Path:
    return Path.home() / ".config" / "autostart" / LINUX_DESKTOP_NAME


def _linux_systemd_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / LINUX_SYSTEMD_NAME


def _install_linux() -> Path:
    exe = _find_executable()

    # Try systemd user service first
    systemd_dir = Path.home() / ".config" / "systemd" / "user"
    systemd_dir.mkdir(parents=True, exist_ok=True)

    service_content = f"""[Unit]
Description=DeskSearch Background Daemon
After=default.target

[Service]
Type=simple
ExecStart={exe} daemon start --no-daemonize
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
"""
    service_path = systemd_dir / LINUX_SYSTEMD_NAME
    service_path.write_text(service_content)

    # Also create XDG autostart .desktop file as fallback
    autostart_dir = Path.home() / ".config" / "autostart"
    autostart_dir.mkdir(parents=True, exist_ok=True)

    desktop_content = f"""[Desktop Entry]
Type=Application
Name=DeskSearch
Comment=Private semantic search for local files
Exec={exe} daemon start
Hidden=false
X-GNOME-Autostart-enabled=true
"""
    desktop_path = autostart_dir / LINUX_DESKTOP_NAME
    desktop_path.write_text(desktop_content)

    logger.info("Installed Linux systemd service: %s", service_path)
    logger.info("Installed Linux autostart: %s", desktop_path)
    return service_path


def _uninstall_linux() -> bool:
    removed = False
    for path in (_linux_systemd_path(), _linux_desktop_path()):
        if path.exists():
            if "systemd" in str(path):
                os.system(f"systemctl --user disable {LINUX_SYSTEMD_NAME} 2>/dev/null")
                os.system(f"systemctl --user stop {LINUX_SYSTEMD_NAME} 2>/dev/null")
            path.unlink()
            logger.info("Removed: %s", path)
            removed = True
    return removed


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def _windows_shortcut_path() -> Path:
    startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup / "DeskSearch.bat"


def _install_windows() -> Path:
    exe = _find_executable()
    path = _windows_shortcut_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Simple batch file to start daemon
    bat_content = f"""@echo off
start /B "" {exe} daemon start
"""
    path.write_text(bat_content)
    logger.info("Installed Windows startup script: %s", path)
    return path


def _uninstall_windows() -> bool:
    path = _windows_shortcut_path()
    if path.exists():
        path.unlink()
        logger.info("Removed Windows startup script: %s", path)
        return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def install_autostart() -> Path:
    """Install autostart entry for the current platform.

    Returns the path to the created file.
    """
    if sys.platform == "darwin":
        return _install_macos()
    elif sys.platform == "win32":
        return _install_windows()
    else:
        return _install_linux()


def uninstall_autostart() -> bool:
    """Remove autostart entry. Returns True if something was removed."""
    if sys.platform == "darwin":
        return _uninstall_macos()
    elif sys.platform == "win32":
        return _uninstall_windows()
    else:
        return _uninstall_linux()


def is_installed() -> bool:
    """Check if autostart is currently installed."""
    if sys.platform == "darwin":
        return _macos_plist_path().exists()
    elif sys.platform == "win32":
        return _windows_shortcut_path().exists()
    else:
        return _linux_systemd_path().exists() or _linux_desktop_path().exists()
