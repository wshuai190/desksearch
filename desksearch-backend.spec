# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('src/ui/dist', 'ui/dist')]
binaries = []
hiddenimports = ['desksearch', 'desksearch.api', 'desksearch.api.server', 'desksearch.api.routes', 'desksearch.api.schemas', 'desksearch.core', 'desksearch.core.search', 'desksearch.core.bm25', 'desksearch.core.dense', 'desksearch.core.fusion', 'desksearch.core.snippets', 'desksearch.indexer', 'desksearch.indexer.pipeline', 'desksearch.indexer.parsers', 'desksearch.indexer.chunker', 'desksearch.indexer.embedder', 'desksearch.indexer.store', 'desksearch.indexer.watcher', 'desksearch.config', 'desksearch.onboarding', 'desksearch.daemon', 'desksearch.plugins', 'uvicorn', 'fastapi', 'tantivy', 'faiss', 'onnxruntime', 'tokenizers', 'huggingface_hub']
tmp_ret = collect_all('desksearch')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('tantivy')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('onnxruntime')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('tokenizers')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['src/desksearch/__main__.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'sentence_transformers', 'scipy', 'sklearn', 'transformers'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='desksearch-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='desksearch-backend',
)
