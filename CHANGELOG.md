# Changelog

All notable changes to DeskSearch are documented here.

## [0.6.0] - 2026-03-28

### Added
- **Connector plugin system** — extensible architecture with 4 built-in connectors:
  - Local files (file system scanning with scheduled sync)
  - Email (.eml/.mbox parsing with sender/subject/date extraction)
  - Chrome bookmarks (reads Chrome profile, folder hierarchy)
  - Slack export (ZIP import with username resolution)
- **ConnectorRegistry** — discover, enable/disable, configure, sync connectors via API
- **Connector API** (`/api/connectors/v2/`) — 6 endpoints for managing data sources
- **Advanced search filters** — filter by file type, date range, file size
- **Sort options** — sort by relevance, date, size, or name
- **Export formats** — results as JSON, CSV, or plain text
- **Favorites system** — bookmark important files via API
- **Recent files** — track recently opened documents
- **ONNX model export** — [Starbucks](https://arxiv.org/abs/2410.13230) 2D Matryoshka model exported to ONNX with INT8 quantization
  - Fast tier: 36MB (INT8) / 145MB (FP32)
  - Middle tier: 50MB (INT8) / 199MB (FP32)
  - Pro tier: 64MB (INT8) / 253MB (FP32)
- **Rust native binary** — complete rewrite of hot paths in Rust
  - 13MB standalone binary
  - PDF/DOCX/PPTX/XLSX parsers
  - Hybrid BM25 + dense search with usearch
  - Embedded web frontend
  - File watcher for live re-indexing
  - ONNX embedding via `ort` crate (load-dynamic)
- **Live indexing progress** — real-time progress bar with phase tracking, throughput, current file
- **`desksearch benchmark`** command for performance testing

### Changed
- **UI overhaul** — dark mode (navy-black palette), indigo/purple accent system, glass morphism
- **Settings redesign** — grouped sections with speed tier visual selector
- **Animations** — slide-up transitions, stagger children, floating logo
- **Responsive layout** — mobile-friendly settings and search
- **FastAPI lifespan** — migrated from deprecated `on_event` handlers
- **Lazy imports** — heavy modules (torch, transformers, FAISS) loaded on demand
- **Removed ORJSONResponse** — FastAPI handles JSON natively now

### Fixed
- Collections/topics/duplicates silently broken (wrong method name on store)
- Settings API missing `search_speed` field
- `POST /api/index` with no body returned 422 instead of indexing configured folders
- `/api/status` crashed due to missing `_compute_index_size_mb` function
- Duplicate `disk_stats()` and `vacuum_if_fragmented()` methods in store
- Dense-only search results missing file paths

### Performance
- **10x embedding speedup** — 171 chunks/sec (ONNX) vs 17 chunks/sec (PyTorch)
- Server startup: **1.3s** (lazy imports)
- 431 tests passing
- Deprecation warnings reduced from 124 to 9

## [0.5.0] - 2026-03-25

### Added
- **Starbucks 2D Matryoshka embeddings** — layer and dimension truncation with 3 speed tiers (fast/middle/pro); see [paper](https://arxiv.org/abs/2410.13230)
- Local model caching — loads only the layers needed per tier, no re-download
- Mock embedder for API tests — eliminates torch/FAISS segfault on Apple Silicon cleanup
- `desksearch benchmark` command for reproducible performance testing
- `desksearch doctor` health check command

### Changed
- Default embedding model switched to `ielabgroup/Starbucks-msmarco` (from all-MiniLM-L6-v2)
- Default embedding dimension reduced to 64d (from 384d) — 6x smaller index
- CLS pooling (trained method) replaces mean pooling
- Improved atexit cleanup to prevent segfaults on shutdown

### Performance
- Search latency p50: 1.11 ms (50K docs, 64d HNSW)
- FAISS raw search: 0.08 ms
- 896 queries/sec sustained throughput

## [0.4.0] - 2026-03-15

### Added
- **Matryoshka embedding truncation** — configurable `embedding_dim` (default 64d)
- Batch embedding pipeline (256 chunks/batch, 3–5x throughput improvement)
- Parallel file parsing with 6 worker threads
- Query expansion with synonym table and morphological variants
- Search result LRU cache (256 entries, invalidated on index mutation)
- `desksearch stats` command with detailed index breakdown
- FAISS auto-selection: FlatIP (<1K), HNSW (1K–50K), IVFFlat (>50K)

### Changed
- Chunking is now sentence-aware with configurable overlap
- Incremental indexing uses content hashing (skip unchanged files)

## [0.3.0] - 2026-02-20

### Added
- **Plugin system** — parser, search, and connector plugin types
- Built-in connectors: email (.eml/.mbox), browser bookmarks, clipboard monitor
- Plugin discovery via `entry_points` and `~/.desksearch/plugins/`
- **Web UI** — React 18 + TypeScript + Vite + Tailwind
- Dark mode, live search, file preview panel, analytics dashboard
- WebSocket endpoint for live indexing progress
- Collections and saved searches
- `desksearch daemon install/uninstall` for macOS LaunchAgent
- API authentication via optional bearer token
- PWA manifest for standalone app mode

### Changed
- API server migrated to FastAPI with async routes
- Daemon log streaming via `daemon logs --follow`

## [0.2.0] - 2026-01-25

### Added
- **Hybrid search** — BM25 (Tantivy) + dense (FAISS) with reciprocal rank fusion
- Configurable RRF alpha parameter (0.0 = BM25 only, 1.0 = dense only)
- Filename and recency boosting in result ranking
- Snippet extraction with query term highlighting
- File watcher (watchdog) for automatic re-indexing
- Background daemon with `desksearch daemon start/stop/status`
- REST API: search, index, files, folders, status, health endpoints
- Support for 30+ file formats (PDF, DOCX, PPTX, XLSX, code, email, archives)
- `desksearch folders add/remove/list` commands
- `--json` flag on all CLI commands

### Changed
- Search results now include snippets and relevance scores
- Index storage moved to `~/.desksearch/` with separate BM25 and dense directories

## [0.1.0] - 2025-12-20

### Added
- Initial release
- BM25 full-text search via Tantivy
- Basic CLI: `desksearch search`, `desksearch index`, `desksearch status`
- SQLite metadata store with FTS5 fallback
- Onboarding wizard with folder auto-detection
- Configuration via `~/.desksearch/config.json`
- Rich terminal output with progress bars
- Document parsing for PDF, DOCX, TXT, Markdown, and common code files
- `desksearch serve` to start local web server on port 3777

## [0.6.1] - 2026-03-28

### Fixed
- Tier naming: "regular" → "middle" (fast / middle / pro)
- Similarity metric: dot product (inner product) instead of cosine — matches Starbucks model training
- Removed incorrect L2 normalization from dense index
- Corrected Starbucks paper author order (Zhuang*, Wang*, Zheng, Koopman, Zuccon)
- Duplicate `disk_stats()` and `vacuum_if_fragmented()` methods in store
- Collections/topics/duplicates silently broken (wrong store method name)
- Settings API missing `search_speed` field
- `POST /api/index` with no body returned 422

### Added
- "Powered by Starbucks Embeddings" section in README with paper citation and BibTeX
- Real screenshots of every UI page (home, search, dashboard, settings, data sources, files)
- Animated SVG terminal demo in README
- Starbucks paper reference in Settings UI and pyproject.toml keywords
