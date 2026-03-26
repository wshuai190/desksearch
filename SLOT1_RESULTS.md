# Slot 1 Results (12:00am–3:00am, March 27 2026)

## What Was Completed

### Phase 1: Document Parsers ✅
- **PDF parser** (`rust/desksearch-indexer/src/parsers/pdf.rs`) — Uses `pdf-extract` crate
- **DOCX parser** (`rust/desksearch-indexer/src/parsers/docx.rs`) — Uses `zip` + `quick-xml`, extracts `<w:t>` elements
- **PPTX parser** (`rust/desksearch-indexer/src/parsers/pptx.rs`) — Uses `zip` + `quick-xml`, extracts `<a:t>` from slides
- **XLSX parser** (`rust/desksearch-indexer/src/parsers/xlsx.rs`) — Uses `calamine`, tab-separated rows per sheet
- All parsers wired into `parsers/mod.rs` (parse_file + is_supported)

### Phase 2: Embedding Integration ✅
- **Python subprocess server** (`scripts/embed_server.py`, 183 lines)
  - JSON-lines protocol over stdin/stdout
  - Loads Starbucks model from `~/.desksearch/models/starbucks-6layer/`
  - Supports variable dim (32/64/128) and layers (2/4/6)
  - CLS token pooling + L2 normalize
  - Commands: ping, embed, shutdown
  - All logs to stderr, protocol on stdout only
  - Tested and working

### Phase 3: Rust Embedding Client + Vector Index ✅
- **EmbedClient** (`rust/desksearch-core/src/embed.rs`, 311 lines)
  - Spawns Python subprocess, JSON-lines communication
  - Methods: new(), ping(), embed(), embed_query(), shutdown()
  - 30s read timeout, graceful Drop cleanup
  - 6 unit tests
- **VectorIndex** (`rust/desksearch-core/src/vector.rs`, 250 lines)
  - Wraps `usearch` with InnerProduct metric
  - M=16, efConstruction=128, ef=64, f32 precision
  - Methods: open_or_create(), add(), remove(), search(), save()
  - Handles persistence (save/reload from disk)
  - 7 unit tests

### Phase 4: Full Pipeline + API ✅
- **Indexing endpoint** (`routes/index.rs`) — POST /api/index: walk→parse→chunk→store→BM25
- **Health endpoint** (`routes/health.rs`) — GET /api/health with uptime tracking
- **Folders endpoint** (`routes/folders.rs`) — GET/POST/DELETE /api/folders
- **Settings endpoint** (`routes/settings.rs`) — GET/PUT /api/settings (JSON merge)
- **Search enhanced** (`routes/search.rs`) — Results now include file metadata (path, filename, file_type, modified, file_size)
- **CLI index command** — Full pipeline in `desksearch index <path>` (walk, parse, chunk, store, BM25 index)
- **AppState updated** — Added start_time, config_path

## Stats
- **Rust lines:** 3,498 (was 2,067 → +1,431 new lines)
- **Python lines:** 183 (embed_server.py)
- **Tests:** 50 passing (25 core + 25 indexer)
- **Binary size:** 11MB release
- **Build:** clean, zero warnings
- **Commit:** `59e36e6` pushed to main

## What Still Needs Work (for Slot 2)

### Integration Wiring (High Priority)
1. **Wire EmbedClient into the indexing pipeline** — Currently BM25-only indexing works but embeddings aren't computed during index. Need to:
   - Spawn EmbedClient in AppState or during index command
   - After chunking, embed each chunk's text via EmbedClient
   - Store vectors in VectorIndex
   - Save VectorIndex after indexing
   
2. **Wire VectorIndex into SearchEngine** — The SearchEngine currently has `// TODO: dense index will be added` placeholder. Need to:
   - Add VectorIndex to SearchEngine struct
   - Embed query via EmbedClient during search
   - Run parallel BM25 + vector search
   - Feed both into existing RRF fusion

### Remaining Pipeline Work
3. **File metadata lookup in search results** — search.rs enriches results from MetadataStore but the chunk_id mapping from BM25 to SQLite needs testing with real indexed data
4. **Incremental re-indexing** — The pipeline uses `needs_reindex()` but doesn't clean up old chunks/vectors when a file changes
5. **File watcher integration** — `notify` crate is a dependency but watcher isn't wired to trigger re-indexing

### Polish
6. **Config file format** — Settings endpoint writes config.json but the server doesn't reload config from it on startup yet
7. **CORS and static file serving** — Need to serve the frontend UI dist files
8. **Error handling in API** — Some endpoints unwrap instead of returning proper error responses
9. **Binary strip** — `cargo build --release` produces 11MB; could be ~7MB with `strip = true` in profile

### New Dependencies Added
```toml
# desksearch-indexer
pdf-extract = "0.7"
zip = "2"
quick-xml = "0.37"
calamine = "0.26"

# desksearch-core (workspace)
usearch = { default-features = false, features = ["fp16lib"] }

# desksearch-server
serde_json (for settings/folders)
```
