# DeskSearch Rust Rewrite Plan

## Goal
Replace Python hot paths with Rust for 10x performance. Keep Python ONLY for
Starbucks embedding inference (PyTorch/ONNX). Everything else moves to Rust.

## Architecture

```
┌─────────────────────────────────────────────┐
│              React UI (unchanged)            │
└──────────────────┬──────────────────────────┘
                   │ HTTP
┌──────────────────▼──────────────────────────┐
│           axum HTTP Server (Rust)            │
│  /search  /index  /status  /settings        │
│  Serves static UI files from embedded dir   │
└──┬──────────┬──────────┬────────────────────┘
   │          │          │
┌──▼───┐  ┌──▼────┐  ┌──▼──────────────────┐
│ BM25 │  │ Dense │  │  Metadata Store     │
│(tantivy)│(usearch)│  │  (SQLite via rusqlite)│
└──────┘  └───────┘  └─────────────────────┘
   ▲          ▲
   │          │
┌──┴──────────┴──────────────────────────────┐
│           Indexing Pipeline (Rust)           │
│  File walker → Parser → Chunker → Store     │
│  Embeddings via PyO3 → Python Starbucks     │
└─────────────────────────────────────────────┘
```

## Crate Structure (Cargo Workspace)

```
rust/
├── Cargo.toml              # Workspace root
├── desksearch-core/        # Search engine, fusion, snippets
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs
│       ├── search.rs       # Hybrid search orchestrator
│       ├── bm25.rs         # tantivy wrapper
│       ├── dense.rs        # usearch/FAISS wrapper
│       ├── fusion.rs       # Weighted RRF
│       └── snippets.rs     # Snippet extraction + highlighting
├── desksearch-indexer/      # File parsing, chunking, store
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs
│       ├── parsers/        # Per-format parsers
│       │   ├── mod.rs
│       │   ├── text.rs     # txt, md, csv, log
│       │   ├── pdf.rs      # PDF via lopdf + pdf-extract
│       │   ├── docx.rs     # DOCX via zip + xml
│       │   ├── html.rs     # HTML via scraper
│       │   └── code.rs     # Code files (tree-sitter optional)
│       ├── chunker.rs      # Text chunking (sentence/paragraph)
│       ├── store.rs        # SQLite metadata store (rusqlite)
│       ├── walker.rs       # Parallel file discovery (ignore crate)
│       └── watcher.rs      # FS watcher (notify crate)
├── desksearch-server/       # axum HTTP server
│   ├── Cargo.toml
│   └── src/
│       ├── main.rs         # Entry point + CLI
│       ├── routes/
│       │   ├── mod.rs
│       │   ├── search.rs
│       │   ├── index.rs
│       │   ├── status.rs
│       │   └── settings.rs
│       ├── state.rs        # App state
│       └── embed_bridge.rs # PyO3 bridge to Python embedder
└── desksearch-pyo3/         # PyO3 module (optional, for hybrid mode)
    ├── Cargo.toml
    └── src/
        └── lib.rs          # Expose Rust search/index to Python
```

## Performance Targets

| Component | Python Current | Rust Target |
|-----------|---------------|-------------|
| File parsing | ~20 files/sec | 500+ files/sec |
| Text chunking | ~1k chunks/sec | 10k+ chunks/sec |
| BM25 search | ~5ms (tantivy-py) | <1ms (tantivy native) |
| Dense search | ~3ms (FAISS) | <1ms (usearch) |
| Hybrid search E2E | ~30ms | <2ms |
| HTTP response | ~10ms overhead | <1ms overhead |
| Memory idle | ~150MB | <50MB |
| Binary size | ~150MB (Electron) | <50MB standalone |
| Startup | ~3s | <500ms |

## Key Rust Dependencies

- **axum** - async HTTP server
- **tantivy** - BM25 full-text search (native, not Python binding)
- **usearch** - dense vector search (or faiss-rs)
- **rusqlite** - SQLite with bundled feature
- **lopdf** / **pdf-extract** - PDF parsing
- **scraper** - HTML parsing
- **zip** - DOCX/PPTX (they're ZIP archives)
- **quick-xml** - XML parsing for Office formats
- **notify** - filesystem watcher
- **ignore** - fast file walker (respects .gitignore)
- **rayon** - parallel processing
- **serde** / **serde_json** - serialization
- **pyo3** - Python interop for embedding model
- **clap** - CLI argument parsing
- **tracing** - structured logging
- **tokio** - async runtime

## Phases

### Phase 1: Foundation (Tonight)
- [x] Install Rust toolchain + maturin
- [ ] Create Cargo workspace with all crates
- [ ] desksearch-core: BM25 search via tantivy (native)
- [ ] desksearch-indexer: text/markdown parser + chunker
- [ ] desksearch-server: basic axum server with /search endpoint
- [ ] Tests for core search functionality

### Phase 2: File Parsing
- [ ] PDF parser (lopdf + pdf-extract)
- [ ] DOCX parser (zip + quick-xml)
- [ ] HTML parser (scraper)
- [ ] Code file parser
- [ ] Parallel file walker with ignore crate
- [ ] Benchmark: 500+ files/sec target

### Phase 3: Search Engine
- [ ] Dense vector search via usearch
- [ ] Weighted RRF fusion
- [ ] Snippet extraction + highlighting
- [ ] Query expansion / understanding
- [ ] Benchmark: <2ms hybrid search

### Phase 4: Server + API
- [ ] Full axum server matching Python API
- [ ] Static file serving (embed React dist)
- [ ] Settings management
- [ ] WebSocket for indexing progress
- [ ] PyO3 bridge for Starbucks embeddings

### Phase 5: Standalone Binary
- [ ] Single binary with embedded UI
- [ ] CLI (clap): `desksearch serve`, `desksearch index`
- [ ] FS watcher integration
- [ ] macOS LaunchAgent support
- [ ] Target: <50MB binary

## Embedding Strategy

Python stays for embedding inference only:
1. **Standalone mode**: Rust binary spawns Python subprocess for embeddings
2. **Hybrid mode**: PyO3 module lets Python call Rust search directly
3. **Future**: ONNX Runtime Rust bindings for full Rust embeddings

## Migration Path

1. Build Rust binary alongside Python version
2. Rust server can read existing SQLite + tantivy indexes
3. Gradual migration: start with search, then indexing, then server
4. Python version stays as fallback during transition

## Safety Rules
- ONLY modify files inside /Users/dylanwang/Projects/localsearch/
- ONLY modify files inside ~/.desksearch/
- Tests before every commit
- `trash` > `rm`
