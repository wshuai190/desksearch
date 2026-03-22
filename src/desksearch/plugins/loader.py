"""Plugin discovery and loading.

Discovers plugins from two sources:
1. ``entry_points`` group ``desksearch.plugins`` (pip-installable plugins).
2. Python files in ``~/.desksearch/plugins/`` (local / development plugins).
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import sys
from pathlib import Path
from typing import Any

from desksearch.plugins.base import BasePlugin
from desksearch.plugins.registry import PluginRegistry

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "desksearch.plugins"
LOCAL_PLUGIN_DIR = Path.home() / ".desksearch" / "plugins"


def _load_entry_point_plugins() -> list[type[BasePlugin]]:
    """Discover plugin classes advertised via ``entry_points``."""
    plugins: list[type[BasePlugin]] = []
    if sys.version_info >= (3, 10):
        from importlib.metadata import entry_points

        eps = entry_points(group=ENTRY_POINT_GROUP)
    else:
        from importlib.metadata import entry_points as _ep

        all_eps = _ep()
        eps = all_eps.get(ENTRY_POINT_GROUP, [])

    for ep in eps:
        try:
            obj = ep.load()
            if isinstance(obj, type) and issubclass(obj, BasePlugin):
                plugins.append(obj)
            else:
                logger.warning(
                    "Entry point %s did not resolve to a BasePlugin subclass", ep.name
                )
        except Exception:
            logger.exception("Failed to load entry point plugin: %s", ep.name)
    return plugins


def _load_local_plugins(directory: Path) -> list[type[BasePlugin]]:
    """Discover plugin classes from .py files in *directory*."""
    plugins: list[type[BasePlugin]] = []
    if not directory.is_dir():
        return plugins

    for py_file in sorted(directory.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        module_name = f"desksearch_local_plugin_{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

            for _name, obj in inspect.getmembers(mod, inspect.isclass):
                if (
                    issubclass(obj, BasePlugin)
                    and obj is not BasePlugin
                    and not inspect.isabstract(obj)
                    and obj.__module__ == mod.__name__
                ):
                    plugins.append(obj)
        except Exception:
            logger.exception("Failed to load local plugin from %s", py_file)
    return plugins


def discover_plugins(
    *,
    enabled: list[str] | None = None,
    plugin_configs: dict[str, dict[str, Any]] | None = None,
    local_dir: Path | None = None,
    registry: PluginRegistry | None = None,
) -> PluginRegistry:
    """Discover, instantiate, and register all available plugins.

    Args:
        enabled: If provided, only load plugins whose ``name`` is in this list.
            ``None`` means load everything found.
        plugin_configs: Per-plugin config dicts keyed by plugin name.
        local_dir: Override the default local plugin directory.
        registry: Existing registry to add to. Creates a new one if ``None``.

    Returns:
        The populated ``PluginRegistry``.
    """
    reg = registry or PluginRegistry()
    plugin_configs = plugin_configs or {}
    scan_dir = local_dir if local_dir is not None else LOCAL_PLUGIN_DIR

    classes: list[type[BasePlugin]] = []
    classes.extend(_load_entry_point_plugins())
    classes.extend(_load_local_plugins(scan_dir))

    for cls in classes:
        try:
            instance = cls()
        except Exception:
            logger.exception("Failed to instantiate plugin class %s", cls.__name__)
            continue

        if enabled is not None and instance.name not in enabled:
            logger.debug("Skipping disabled plugin: %s", instance.name)
            continue

        cfg = plugin_configs.get(instance.name)
        reg.register(instance, config=cfg)

    return reg
