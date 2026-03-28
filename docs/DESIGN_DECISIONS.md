# Design Decisions — Performance & UX

## 1. Search Must Be INSTANT (<50ms)

### Problem
Users expect Google-speed search. Loading a sentence-transformer model takes 2-5 seconds. Embedding a query takes 50-200ms. This is too slow for keystroke-by-keystroke search.

### Solution: Dual-Mode Search
- **Phase 1 (instant, <10ms):** BM25 only via tantivy (Rust-based, sub-millisecond). Results appear as you type.
- **Phase 2 (background, <200ms):** Dense embedding search runs in background, results merge in via RRF. UI smoothly updates.
- **Startup:** Tantivy index loads in <100ms from memory-mapped files. Dense index loads async in background.
- **Model pre-loading:** Embedding model loaded once at startup, stays in memory. First search may have 1-2s delay for model load, then instant.

### Alternative Considered
- Pre-compute query embeddings for common terms → too much storage, stale
- Use ONNX runtime instead of PyTorch → 3-5x faster inference, should implement in v0.2

## 2. App-Like Experience

### Problem
`pip install` + `desksearch serve` is developer-friendly but not consumer-friendly. Regular users want to download an app.

### Solution: Progressive Packaging
- **v0.1 (now):** pip install + CLI. Target: developers and power users.
- **v0.2:** System tray app using `pystray`. Runs in background, menubar icon, opens web UI in browser.
- **v0.3:** Electron or Tauri desktop app. Single .dmg/.exe download. Bundles Python runtime + models.
- **v1.0:** Native macOS app (Swift) / Windows app. Proper file system integration.

### For MVP: System Tray Daemon
```
desksearch install-daemon  # Creates LaunchAgent (macOS) or service (Linux/Windows)
                           # App starts on login, sits in system tray
                           # Click tray icon → opens search in browser
                           # Keyboard shortcut: Cmd+Shift+Space → instant search
```

## 3. Search Quality (This is the differentiator)

### Why Our Search Is Better Than Spotlight/Windows Search
1. **Hybrid retrieval:** BM25 catches exact terms, dense catches semantic meaning. Neither alone is sufficient.
2. **Reciprocal Rank Fusion:** Principled way to combine two ranking signals (Dylan's IR expertise).
3. **Smart chunking:** Paragraph-aware, respects document structure. Not blind character splits.
4. **Query understanding:** Detect query type (keyword vs question vs phrase) and adjust retrieval strategy.
5. **Snippet quality:** Show the MOST RELEVANT passage, not just the first occurrence.

### Ranking Pipeline (v0.2+)
```
Query → Query Analysis → BM25 Search + Dense Search → RRF Fusion → Reranker (cross-encoder) → Results
```
Adding a cross-encoder reranker (e.g., ms-marco-MiniLM) on top-20 fused results would dramatically improve precision. This is standard in production search but NO local search tool does it.

## 4. Indexing Must Be Background & Non-Intrusive

### Requirements
- First index: scan + parse + embed all files. May take 5-30 min depending on corpus size.
- Incremental: file watcher detects changes, re-indexes only modified files. <1s per file.
- CPU usage: cap embedding at 50% CPU. Don't make the laptop fan spin up.
- Disk usage: index should be <10% of original corpus size.

### Implementation
- Use ThreadPoolExecutor with max_workers=2 for embedding (limits CPU)
- Batch embed: collect 32 chunks, embed in one call (much faster than 1-by-1)
- Progress reporting via WebSocket to UI
- Pause/resume indexing

## 5. Embedding Model Choice

### For MVP: all-MiniLM-L6-v2
- 80MB model, loads fast
- 384-dim embeddings (small index)
- Good quality for general text
- Runs on CPU in ~5ms per query

### For v0.2: User-selectable
- Option to use larger models (e5-large, bge-base) for better quality
- ONNX runtime for 3-5x speedup
- Apple Silicon MPS acceleration

### For v1.0: Custom model
- Train a model specifically optimized for local file search
- Matryoshka embeddings (Dylan's Starbucks work) for flexible dim/precision tradeoff
- This is the ultimate differentiator — a model trained FOR this exact use case

## 6. Global Keyboard Shortcut

Critical for adoption. Users should be able to:
- Press `Cmd+Shift+Space` (configurable) from anywhere
- Search bar pops up immediately
- Type query → instant results
- Press Enter → open file
- Press Escape → dismiss

Implementation: Requires native integration.
- macOS: NSEvent global monitor (Swift helper or pyobjc)
- Linux: X11/Wayland hotkey binding
- Windows: RegisterHotKey

## 7. File Type Priority Ranking

Not all files are equal. A matching PDF in ~/Documents is more relevant than a .pyc in node_modules.

Default boosts:
- Documents (.pdf, .docx, .md): 1.5x
- Notes/text (.txt, .org): 1.3x
- Code (.py, .js): 1.0x
- Config (.json, .yaml, .toml): 0.8x
- Recent files: 1.2x boost for files modified in last 7 days
- Frequently opened: track open count, boost popular files

## 8. Privacy & Security

- ALL processing local. No network calls except to download embedding model (one-time).
- Index stored in ~/.desksearch/ with user-only permissions (0700).
- No telemetry, no analytics, no phone home.
- Option to encrypt index at rest (v0.3).
- Excluded paths: .ssh, .gnupg, .env files with secrets auto-excluded.
