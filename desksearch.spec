# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for DeskSearch backend binary.

Produces a single-folder distribution at dist/desksearch-backend/
that can be bundled into the Electron app.

Build:
    cd /Users/dylanwang/Projects/localsearch
    source .venv/bin/activate
    pyinstaller desksearch.spec
"""

import sys
from pathlib import Path

block_cipher = None

project_root = Path(SPECPATH)
src_dir = project_root / "src"
ui_dist = project_root / "src" / "ui" / "dist"
desksearch_pkg = project_root / "src" / "desksearch"

a = Analysis(
    [str(src_dir / "desksearch" / "__main__.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=[
        # Include the built UI
        (str(ui_dist), "desksearch/ui_dist"),
    ],
    hiddenimports=[
        "desksearch",
        "desksearch.api",
        "desksearch.api.server",
        "desksearch.api.routes",
        "desksearch.api.schemas",
        "desksearch.api.integrations",
        "desksearch.core",
        "desksearch.core.search",
        "desksearch.core.bm25",
        "desksearch.core.dense",
        "desksearch.core.fusion",
        "desksearch.core.snippets",
        "desksearch.core.collections",
        "desksearch.indexer",
        "desksearch.indexer.embedder",
        "desksearch.indexer.pipeline",
        "desksearch.indexer.store",
        "desksearch.indexer.watcher",
        "desksearch.plugins",
        "desksearch.plugins.base",
        "desksearch.plugins.loader",
        "desksearch.plugins.registry",
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "fastapi",
        "starlette",
        "pydantic",
        "tantivy",
        "faiss",
        "onnxruntime",
        "tokenizers",
        "watchdog",
        "psutil",
        "orjson",
        "aiofiles",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",  # Starbucks model uses torch — too heavy for standalone binary
        "transformers",
        "sentence_transformers",
        "matplotlib",
        "tkinter",
        "PIL",
        "scipy",  # Save space — not needed at runtime
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="desksearch-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=[],
    name="desksearch-backend",
)
