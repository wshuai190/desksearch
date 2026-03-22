# DeskSearch — Private Semantic Search Engine for Your Files

## Vision
A fast, beautiful, private semantic search engine that runs entirely on your laptop.
Index everything — documents, emails, notes, code, images — and find anything by asking in natural language.
"Perplexity for your own files."

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                  Web UI (React)                  │
│   Search bar → Results with snippets & sources   │
│   File preview │ Filters │ Collections           │
└──────────────────────┬──────────────────────────┘
                       │ HTTP/WebSocket
┌──────────────────────▼──────────────────────────┐
│              FastAPI Backend (Python)             │
│   /search  /index  /status  /settings            │
│   Query understanding → Hybrid retrieval →       │
│   Reranking → Snippet extraction                 │
└──────┬───────────┬───────────┬──────────────────┘
       │           │           │
┌──────▼──┐ ┌─────▼────┐ ┌───▼──────────────────┐
│ BM25    │ │  Dense   │ │   Metadata Store     │
│ Index   │ │  Index   │ │   (SQLite)           │
│(tantivy)│ │ (FAISS/  │ │   file paths, dates, │
│         │ │  usearch)│ │   types, thumbnails  │
└─────────┘ └──────────┘ └──────────────────────┘
       ▲           ▲
       │           │
┌──────┴───────────┴──────────────────────────────┐
│              Indexing Pipeline                    │
│   File watcher (watchdog) → Parser → Chunker →   │
│   Embedder (local model) → Index writer          │
│                                                  │
│   Parsers: PDF(marker) │ DOCX │ TXT │ MD │ Code │
│            Images(OCR) │ Email(.eml) │ HTML      │
└─────────────────────────────────────────────────┘
```

## Tech Stack

### Core (Python)
- **FastAPI** — async API server
- **SQLite + FTS5** — metadata store + full-text fallback
- **tantivy-py** — fast BM25 index (Rust-based, way faster than Whoosh)
- **FAISS or usearch** — dense vector index
- **sentence-transformers** — local embedding model (all-MiniLM-L6-v2 for MVP, upgrade later)
- **watchdog** — filesystem watcher for live indexing

### Document Parsing
- **marker** — PDF → markdown (best quality)
- **python-docx** — Word documents
- **python-pptx** — PowerPoint
- **openpyxl** — Excel
- **beautifulsoup4** — HTML/emails
- **Pillow + pytesseract** — OCR for images/screenshots
- **tree-sitter** — code files (syntax-aware chunking)

### UI (React + Vite)
- **React 18** with TypeScript
- **Tailwind CSS** — styling
- **Vite** — build tool
- Clean, minimal Perplexity-inspired design
- File preview panel
- Search filters (date, file type, folder)

### Packaging
- **pip install desksearch** — Python package
- **brew install desksearch** — macOS (later)
- Single command to start: `desksearch serve`
- Auto-indexes ~/Documents, ~/Desktop, ~/Downloads by default

## Key Design Decisions

1. **100% Local** — No cloud, no API keys needed for MVP. Embedding model runs locally.
2. **Hybrid Search** — BM25 + dense embeddings + reciprocal rank fusion. This is where Dylan's expertise shines.
3. **Incremental Indexing** — File watcher detects changes, only re-indexes modified files.
4. **Chunk with Context** — Each chunk stores parent document reference for full-context answers.
5. **Fast Startup** — Index persists on disk. Startup = load index + start server. Should be <2 seconds.

## MVP Scope (v0.1)

### Must Have
- [ ] Index text files: .txt, .md, .pdf, .docx
- [ ] Hybrid search: BM25 + dense embeddings
- [ ] Reciprocal rank fusion for combining results
- [ ] Web UI with search bar and results
- [ ] File snippets with highlighted matches
- [ ] Click result → open file in system default app
- [ ] CLI: `desksearch index <path>` and `desksearch serve`
- [ ] Incremental indexing (only new/changed files)
- [ ] Basic filters: file type, date range

### Nice to Have (v0.2)
- [ ] Image OCR indexing
- [ ] Code-aware indexing (tree-sitter)
- [ ] Answer generation (LLM summarizes top results)
- [ ] Email indexing (.eml, .mbox)
- [ ] Collections / saved searches
- [ ] System tray app (background daemon)

### Future (v1.0)
- [ ] macOS native app
- [ ] Browser extension (index bookmarks)
- [ ] Slack/Discord/Gmail integrations (premium)
- [ ] Team/shared search (premium)
- [ ] Mobile companion app

## Agent Assignments

### Agent 1: Core Search Engine (src/core/)
- Hybrid retrieval: BM25 (tantivy) + dense (FAISS)
- Reciprocal rank fusion
- Query processing
- Result ranking and snippet extraction
- Tests

### Agent 2: Indexing Pipeline (src/indexer/)
- File discovery and watching
- Document parsing (PDF, DOCX, TXT, MD, code)
- Chunking strategies
- Embedding generation
- SQLite metadata store
- Incremental index updates
- Tests

### Agent 3: API Server (src/api/)
- FastAPI endpoints: /search, /index, /status, /settings
- WebSocket for live indexing progress
- CORS for UI
- Settings management
- Tests

### Agent 4: Web UI (src/ui/)
- React + Vite + Tailwind
- Search interface (Perplexity-inspired)
- Results display with snippets, file icons, dates
- File type/date filters
- File preview panel
- Settings page (indexed folders, reindex trigger)

## File Structure
```
desksearch/
├── pyproject.toml
├── README.md
├── ARCHITECTURE.md
├── src/
│   ├── __init__.py
│   ├── __main__.py          # CLI entry point
│   ├── config.py            # Settings/configuration
│   ├── core/
│   │   ├── __init__.py
│   │   ├── search.py        # Hybrid search engine
│   │   ├── bm25.py          # Tantivy BM25 wrapper
│   │   ├── dense.py         # FAISS/usearch dense index
│   │   ├── fusion.py        # Reciprocal rank fusion
│   │   └── snippets.py      # Snippet extraction & highlighting
│   ├── indexer/
│   │   ├── __init__.py
│   │   ├── pipeline.py      # Main indexing pipeline
│   │   ├── watcher.py       # Filesystem watcher
│   │   ├── parsers.py       # Document parsers
│   │   ├── chunker.py       # Text chunking
│   │   ├── embedder.py      # Local embedding model
│   │   └── store.py         # SQLite metadata store
│   ├── api/
│   │   ├── __init__.py
│   │   ├── server.py        # FastAPI app
│   │   ├── routes.py        # API endpoints
│   │   └── schemas.py       # Pydantic models
│   └── ui/                  # React app (built separately)
│       ├── package.json
│       ├── vite.config.ts
│       ├── index.html
│       ├── src/
│       │   ├── App.tsx
│       │   ├── components/
│       │   │   ├── SearchBar.tsx
│       │   │   ├── ResultsList.tsx
│       │   │   ├── ResultCard.tsx
│       │   │   ├── FilePreview.tsx
│       │   │   └── Filters.tsx
│       │   ├── hooks/
│       │   │   └── useSearch.ts
│       │   └── styles/
│       │       └── globals.css
│       └── tailwind.config.js
├── tests/
│   ├── test_search.py
│   ├── test_indexer.py
│   └── test_api.py
└── data/                    # Default index storage
    └── .gitkeep
```
