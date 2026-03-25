# DeskSearch Rust Sprint 2 — Mar 27, 2026 (12am–6am)

## Context
Sprint 1 (Mar 26) scaffolded the Rust workspace: 2,067 lines across 3 crates.
We have: tantivy BM25, RRF fusion, text/HTML parsers, chunker, SQLite store, axum server.
Binary: 7.1MB. Compiles clean.

## What's Missing (Priority Order)
1. **PDF parser** — biggest gap, most common file type
2. **DOCX/PPTX/XLSX parsers** — office docs
3. **Embedding integration** — need to call Starbucks ONNX/PyTorch from Rust
4. **Vector search** — usearch/FAISS wiring (crate added but not integrated)
5. **Frontend serving** — embed React dist in the binary (rust-embed)
6. **Full API parity** — all Python endpoints reimplemented
7. **File watcher** — live reindex on file changes (notify crate)
8. **Config system** — read ~/.desksearch/config.json
9. **End-to-end test** — index real folder, search, verify results

## Targets
| Metric | Target |
|--------|--------|
| Binary size | <10MB |
| Startup | <50ms |
| Index 1000 files | <30s |
| Search latency | <1ms |
| Memory idle | <30MB |
| Memory indexing | <200MB |

## Phase 1: Document Parsers (12:00–1:00am) — 3 agents
### Agent 1a: PDF Parser
- Use `pdf-extract` or `lopdf` crate
- Extract text from each page, concatenate
- Handle encrypted/malformed PDFs gracefully (skip, don't crash)
- Test with real PDFs of varying sizes

### Agent 1b: Office Parsers
- DOCX: `docx-rs` crate (zip → XML → text)
- PPTX: zip → XML slides → extract text from each slide
- XLSX: `calamine` crate → iterate sheets → extract cell text
- Each parser in its own file under parsers/

### Agent 1c: Additional Parsers
- Markdown: strip formatting, keep content (pulldown-cmark)
- Email (.eml): `mailparse` crate → subject + from + body
- Code files: already handled by text parser, but add language detection
- Archives (.zip/.tar): extract and parse inner files (max 100 files, 50KB each)

## Phase 2: Embedding Integration (1:00–2:00am) — 2 agents
### Agent 2a: Python Subprocess for Embedding
- Spawn a Python subprocess that loads the Starbucks model
- Communicate via stdin/stdout JSON-lines protocol:
  - Request: `{"texts": ["chunk1", "chunk2", ...], "tier": "regular"}`
  - Response: `{"embeddings": [[0.1, 0.2, ...], ...]}`
- Connection pooling: keep subprocess alive, reuse for batches
- Timeout: kill and restart if no response in 30s
- Create `scripts/embed_server.py` — standalone Python embedding worker

### Agent 2b: Vector Search with usearch
- Wire up usearch crate for approximate nearest neighbor
- HNSW index with configurable M and efSearch
- Support add, remove, search operations
- Save/load index to disk (~/.desksearch/vectors.usearch)
- Integrate into the search pipeline alongside tantivy BM25

## Phase 3: Full Search Pipeline (2:00–2:30am)
- Wire everything together: query → embed → parallel BM25 + vector → RRF → snippets → respond
- The search endpoint should return identical JSON schema to Python version
- Test: index a folder of mixed files, search, verify quality

## Phase 4: Frontend & API Parity (2:30–3:30am) — 2 agents
### Agent 4a: Embed Frontend
- Use `rust-embed` to bundle the React dist/ into the binary
- Serve at / with proper MIME types
- SPA fallback: all non-API routes serve index.html

### Agent 4b: API Parity
- Reimplement all Python API endpoints:
  - GET /api/status
  - GET /api/search?q=...&top_k=...
  - GET /api/folders
  - POST /api/folders
  - DELETE /api/folders/{path}
  - POST /api/index
  - GET /api/index/status
  - DELETE /api/index/clear
  - GET /api/settings
  - PUT /api/settings
  - GET /api/health
- Same JSON schema as Python version (frontend compatibility)

## Phase 5: File Watcher + Config (3:30–4:00am)
- `notify` crate for filesystem watching
- Watch all configured folders, debounce 2s
- On file change: reparse → rechunk → re-embed → update index
- Config: read ~/.desksearch/config.json with serde
- Support all existing config fields (search_speed, embedding_dim, etc.)

## Phase 6: CLI Commands (4:00–4:30am)
- `desksearch serve` — start the server
- `desksearch index <path>` — index a directory
- `desksearch search <query>` — search from CLI
- `desksearch status` — show index stats
- `desksearch config` — show/edit configuration
- `desksearch benchmark` — run search benchmarks

## Phase 7: Testing & Benchmarks (4:30–5:30am)
- Rust unit tests for each module
- Integration test: index real folder → search → verify results
- Benchmark comparison: Rust vs Python on same dataset
- Memory profiling with real data
- Fix any bugs found

## Phase 8: Build & Release (5:30–6:00am)
- `cargo build --release` — ensure clean build
- Run `strip` on binary if not already
- Update README with Rust installation option
- Commit, push, tag
- WhatsApp final summary with benchmark numbers

---

## SAFETY RULES
1. ONLY modify files inside /Users/dylanwang/Projects/localsearch/ and ~/.desksearch/
2. NEVER delete or modify files outside the project
3. READ-ONLY access to other folders for testing
4. No system-level changes
5. Keep server on 127.0.0.1

## Technical Details
- Repo: /Users/dylanwang/Projects/localsearch
- Rust dir: /Users/dylanwang/Projects/localsearch/rust/
- Python venv: source .venv/bin/activate (for embedding subprocess)
- Node: /opt/homebrew/Cellar/node@22/22.22.0_1/bin
- 8GB Mac mini ARM
- GitHub: https://github.com/wshuai190/desksearch
- DO NOT commit publish-pypi.sh
