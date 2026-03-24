# DeskSearch Rust Core Rewrite — Mar 26, 2026 (12am–6am)

## Goal
Replace Python hot paths with Rust via PyO3 bindings. Keep Python only for ML inference.
Target: single binary <100MB, <100ms startup, 10x parsing speed, 1/5 memory.

## Architecture After Rewrite
```
┌─────────────────────────────────────────┐
│  React Frontend (unchanged)              │
├─────────────────────────────────────────┤
│  Rust Core (axum HTTP server)            │
│  ├── File discovery & watching           │
│  ├── Parallel file parsing (rayon)       │
│  ├── Text chunking (zero-copy)           │
│  ├── SQLite index (rusqlite)             │
│  ├── tantivy BM25 (already Rust)         │
│  ├── FAISS bindings (C++ FFI)            │
│  └── Search orchestration & RRF fusion   │
├─────────────────────────────────────────┤
│  Python subprocess (embedding only)      │
│  └── Starbucks model via ONNX/PyTorch    │
└─────────────────────────────────────────┘
```

## Approach: Hybrid via PyO3 (not full rewrite)
Instead of rewriting everything from scratch, build a Rust library (`desksearch-core`)
that Python calls via PyO3. This lets us:
1. Replace hot paths incrementally (parsing → chunking → search → server)
2. Keep all existing Python tests working during migration
3. Ship as a Python package with native extension (maturin build)
4. Eventually: standalone Rust binary that embeds Python only for embedding

## Phase 1: Rust Project Setup (12:00–12:30am)
- Create `rust/` directory with Cargo workspace
- Set up PyO3 + maturin for Python bindings
- Configure rayon for parallelism
- Add dependencies: tantivy, rusqlite, axum, tokio, rayon, serde

## Phase 2: File Parsing in Rust (12:30–1:30am) — BIGGEST WIN
Current Python parsing is the #1 bottleneck. Rewrite in Rust:
- Plain text / code files: read_to_string (trivial, 100x faster than Python IO)
- PDF: use `pdf-extract` or `lopdf` crate
- DOCX/PPTX/XLSX: use `docx-rs`, `calamine` crates (or zip + xml parsing)
- Markdown/HTML: `pulldown-cmark`, `scraper` crates
- Email (.eml): `mailparse` crate
- Archives: `zip`, `tar`, `flate2` crates
- Expose via PyO3: `parse_file(path: str) -> str`
- Benchmark: target 500+ files/sec (vs current ~100/sec Python)

## Phase 3: Text Chunking in Rust (1:30–2:00am)
- Sentence-aware chunking with configurable size/overlap
- Unicode-safe splitting (no breaking mid-character)
- Zero-copy where possible (return references into original text)
- Expose: `chunk_text(text: str, size: int, overlap: int) -> list[str]`
- Benchmark: target 10,000+ chunks/sec

## Phase 4: Search Engine in Rust (2:00–3:00am)
- Move tantivy BM25 management to Rust (currently wrapped in Python)
- Implement RRF fusion in Rust (currently Python numpy)
- FAISS: call via C FFI from Rust (faiss-rs crate or raw bindings)
- Query pipeline: tokenize → parallel BM25+dense → RRF → rank → return
- Expose: `search(query: str, top_k: int) -> list[Result]`
- Target: <2ms end-to-end search at 50k docs

## Phase 5: HTTP Server in Rust (3:00–4:00am)
- Replace FastAPI with axum (Rust async web framework)
- Serve the React frontend as static files
- All API endpoints reimplemented in Rust
- WebSocket support for real-time indexing progress
- Keep Python embedding as a subprocess (stdin/stdout JSON protocol)
- Target: <1ms request overhead (vs ~5ms FastAPI)

## Phase 6: Standalone Binary (4:00–5:00am)
- Build with `cargo build --release`
- Embed the React frontend (rust-embed crate)
- Bundle ONNX Runtime as shared library
- Starbucks model: download on first run (same as current)
- Target binary size: <50MB (vs 938MB current)
- Target startup: <100ms to first request

## Phase 7: Integration & Testing (5:00–5:45am)
- Run all existing Python tests against the Rust backend
- Benchmark comparison: Python vs Rust on same dataset
- Fix any compatibility issues
- Update Electron app to use Rust binary instead of PyInstaller

## Phase 8: Final (5:45–6:00am)
- Commit, push, tag
- WhatsApp Dylan with benchmark comparison table

---

## SAFETY RULES (same as always)
1. ONLY modify files inside /Users/dylanwang/Projects/localsearch/ and ~/.desksearch/
2. NEVER delete or modify files outside the project
3. READ-ONLY access to other folders for testing
4. No system-level changes
5. Keep server on 127.0.0.1

## Technical Details
- Repo: /Users/dylanwang/Projects/localsearch
- Rust dir: /Users/dylanwang/Projects/localsearch/rust/
- Python venv: source .venv/bin/activate
- Node: /opt/homebrew/Cellar/node@22/22.22.0_1/bin
- 8GB Mac mini (ARM) — Rust is perfect for memory-constrained
- GitHub: https://github.com/wshuai190/desksearch
- PyPI token in publish-pypi.sh (DO NOT commit)
