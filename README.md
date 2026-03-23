<p align="center">
  <img src="docs/logo.png" alt="DeskSearch" width="64" />
</p>

<h1 align="center">DeskSearch</h1>

<p align="center">
  <strong>Search your files by meaning, not just keywords. 100% local, zero cloud.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/desksearch/"><img src="https://img.shields.io/pypi/v/desksearch?color=%2334D058&label=pypi" /></a>
  <a href="https://github.com/wshuai190/desksearch/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" /></a>
  <a href="https://github.com/wshuai190/desksearch/actions"><img src="https://img.shields.io/github/actions/workflow/status/wshuai190/desksearch/ci.yml?label=tests" /></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" />
</p>

<p align="center">
  <img src="docs/screenshot.png" alt="DeskSearch Demo" width="720" />
</p>

---

> **What does DeskSearch do?**  
> You type *"meeting notes from last Tuesday"* or *"that ML paper about sparse attention"* and DeskSearch finds the right file — even if those exact words aren't in it. Everything runs on your machine. Nothing is ever sent anywhere.

---

## ✨ Features

| | |
|---|---|
| 🔍 **Semantic search** | Finds files by *meaning* using 384-dim neural embeddings — not just keyword matching |
| ⚡ **Hybrid ranking** | Combines BM25 (keyword speed) + FAISS (semantic precision) via Reciprocal Rank Fusion |
| 🔒 **100% private** | No cloud, no API keys, no telemetry. Your data never leaves your machine |
| 📄 **30+ file formats** | PDF, DOCX, Markdown, HTML, Jupyter notebooks, source code, CSV, LaTeX, and more |
| 🖥️ **Web UI** | Clean dark-mode interface at `localhost:3777` — open from any browser |
| 💻 **Rich CLI** | Search, index, and manage everything from the terminal with pretty output |
| 🐍 **Python SDK** | Import DeskSearch directly in your scripts and notebooks |
| 🔄 **Background daemon** | Watches folders and re-indexes new files automatically |
| 🔌 **Plugins** | Extend with custom parsers, rerankers, or data connectors |
| 🐳 **Docker** | One-liner container deployment |

---

## 🚀 Quick Start

**3 steps to searchable files:**

```bash
# 1. Install
pip install desksearch

# 2. Index your documents
desksearch index ~/Documents

# 3. Search
desksearch search "quarterly revenue report"
```

Or launch the web UI:

```bash
desksearch serve   # opens http://localhost:3777
```

---

## 📦 Installation

### pip (recommended for developers)

```bash
pip install desksearch
```

### Desktop App

Download a standalone app (no Python required):

| Platform | Download |
|----------|----------|
| macOS (Apple Silicon) | [Download `.dmg`](https://github.com/wshuai190/desksearch/releases) |
| Windows | [Download `.exe`](https://github.com/wshuai190/desksearch/releases) |
| Linux | [Download `.AppImage`](https://github.com/wshuai190/desksearch/releases) |

### Docker

```bash
docker run -d \
  -p 3777:3777 \
  -v desksearch-data:/data \
  -v ~/Documents:/docs:ro \
  ghcr.io/wshuai190/desksearch

# Then index your docs:
docker exec <container> desksearch index /docs
```

---

## 💻 CLI Reference

### Search

```bash
desksearch search "query"               # Basic search
desksearch search "ML papers" -n 5      # Limit results
desksearch search "budget" --type pdf   # Filter by file type
desksearch search "notes" --json        # Machine-readable output
```

### Indexing

```bash
desksearch index ~/Documents            # Index a folder
desksearch index ~/Papers ~/Notes       # Multiple paths at once
desksearch index ./project --json       # JSON output for scripts
```

### Status & Health

```bash
desksearch status                       # Index stats (docs, chunks, disk)
desksearch stats                        # Detailed breakdown (FAISS, BM25, SQLite)
desksearch doctor                       # Health check — verifies all components
```

### Folder Management

```bash
desksearch folders list                 # Show all watched folders
desksearch folders add ~/Research       # Add a folder to auto-watch
desksearch folders remove ~/Downloads  # Remove a folder
```

### Configuration

```bash
desksearch config show                  # View all settings
desksearch config set port 4000         # Change the server port
desksearch config set chunk_size 256    # Change chunk size
```

### Background Daemon

```bash
desksearch daemon start                 # Start background watcher
desksearch daemon status                # Check if daemon is running
desksearch daemon stop                  # Stop daemon
desksearch daemon install               # Auto-start on login
desksearch daemon logs --follow         # Stream daemon logs
```

### Every command accepts `--help` and `--json`:

```bash
desksearch search --help                # Detailed help with examples
desksearch status --json | jq .         # JSON output for scripts
```

---

## 🐍 Python SDK

Use DeskSearch directly in your Python code:

```python
from desksearch import DeskSearch

# Connect to your index (default: ~/.desksearch)
ds = DeskSearch()

# Search
results = ds.search("quarterly revenue report", limit=5)
for r in results:
    print(f"{r.rank}. {r.filename}  score={r.score:.3f}")
    print(f"   {r.path}")
    print(f"   {r.snippet}\n")

# Index a folder
stats = ds.index("~/Documents/Papers")
print(f"Indexed {stats['indexed']} files ({stats['errors']} errors)")

# Get stats
info = ds.info()
print(f"{info['documents']} documents, {info['disk_usage_mb']:.1f} MB")
```

Use it as a context manager to release resources automatically:

```python
with DeskSearch("~/.desksearch") as ds:
    results = ds.search("todo items", file_type="md")
```

### `SearchResult` fields

| Field | Type | Description |
|-------|------|-------------|
| `rank` | `int` | 1-based position |
| `filename` | `str` | File name (e.g. `report.pdf`) |
| `path` | `str` | Absolute path to file |
| `extension` | `str` | Extension without dot (`pdf`, `md`) |
| `score` | `float` | Relevance score (higher = better) |
| `snippet` | `str` | Matched text excerpt |

### `DeskSearch` methods

| Method | Description |
|--------|-------------|
| `search(query, limit=10, file_type=None)` | Search and return `list[SearchResult]` |
| `index(path, verbose=False)` | Index a file or directory, return stats dict |
| `info()` | Return index stats dict |
| `close()` | Release resources |

---

## ⚙️ Configuration

Config lives at `~/.desksearch/config.json`.  Edit with `desksearch config set KEY VALUE`.

| Key | Default | Description |
|-----|---------|-------------|
| `index_paths` | `~/Documents, ~/Desktop` | Folders to watch and index |
| `embedding_model` | `all-MiniLM-L6-v2` | Sentence-transformer model |
| `chunk_size` | `512` | Characters per text chunk |
| `chunk_overlap` | `64` | Overlap between consecutive chunks |
| `port` | `3777` | Web UI port |
| `max_file_size_mb` | `50` | Skip files larger than this |
| `api_key` | `null` | Bearer token for API auth (optional) |

---

## 🏗️ Architecture

```
Your Files (PDF, DOCX, Markdown, Code, ...)
              │
              ▼  Parse → Chunk → Embed
   ┌──────────────────────────────────┐
   │   30+ parsers  →  512-char chunks │
   │   → all-MiniLM-L6-v2 (ONNX)     │
   └───────────┬──────────────────────┘
               │
       ┌───────┴────────┐
       ▼                ▼
  BM25 (tantivy)    FAISS (dense)
  keyword index     semantic index
       │                │
       └───────┬────────┘
               ▼
    Reciprocal Rank Fusion
               │
               ▼
     Ranked Results + Snippets
```

**Data flow:**
1. **Parse** — extract plain text from 30+ file formats (PDF via PyMuPDF, DOCX, HTML, code, etc.)
2. **Chunk** — split into overlapping 512-char passages for fine-grained retrieval
3. **Embed** — encode each chunk with `all-MiniLM-L6-v2` running locally via ONNX Runtime (~4ms/chunk on M1)
4. **Index** — store in both a tantivy BM25 index and a FAISS flat/IVF dense index
5. **Search** — query both indexes in parallel, re-rank results with Reciprocal Rank Fusion
6. **Snippet** — extract the most relevant sentence from the matched chunk

**Storage layout** (`~/.desksearch/`):

```
~/.desksearch/
├── config.json          # User config
├── metadata.db          # SQLite: file metadata + chunk text
├── dense/               # FAISS vector index
└── bm25/                # Tantivy BM25 index
```

---

## ⚡ Performance

Benchmarked on MacBook Pro M1 (10,000 documents, ~2 GB):

| Metric | Value |
|--------|-------|
| BM25 search latency | < 10 ms |
| Semantic search latency | < 200 ms |
| Indexing throughput | ~100–200 files/sec |
| Memory (idle, daemon) | ~80 MB |
| Cold start | ~1.5 s |
| Embedding model size | ~23 MB (ONNX) |

Run your own benchmark:

```bash
desksearch benchmark                    # 200 synthetic files
desksearch benchmark --files 1000       # Larger run
desksearch benchmark --dir ~/Documents  # Your real files
```

---

## 🔌 Plugins

Three extension points: **parsers**, **search plugins**, and **connectors**.

Drop a `.py` file into `~/.desksearch/plugins/`:

```python
# ~/.desksearch/plugins/my_parser.py
from desksearch.plugins.base import BaseParserPlugin
from pathlib import Path

class EpubParser(BaseParserPlugin):
    name = "epub-parser"
    extensions = [".epub"]

    def parse(self, file_path: Path) -> str:
        import ebooklib
        from ebooklib import epub
        book = epub.read_epub(str(file_path))
        texts = [
            item.get_body_content().decode()
            for item in book.get_items()
            if item.get_type() == ebooklib.ITEM_DOCUMENT
        ]
        return "\n".join(texts)
```

See [PLUGINS.md](PLUGINS.md) for the full plugin API.

---

## 🛠️ Development

```bash
# Clone and install in editable mode
git clone https://github.com/wshuai190/desksearch
cd desksearch
pip install -e ".[dev]"

# Run tests
pytest

# Run with a test data directory
desksearch --data-dir /tmp/test-search index ~/Documents/test
```

### Project layout

```
src/desksearch/
├── __init__.py          # Package entry + Python SDK exports
├── _sdk.py              # DeskSearch SDK class
├── __main__.py          # CLI (Click + Rich)
├── config.py            # Pydantic config model
├── onboarding.py        # First-run wizard
├── api/                 # FastAPI REST server
├── core/                # Search engine (BM25, FAISS, fusion, snippets)
├── indexer/             # Parser, chunker, embedder, pipeline
├── daemon/              # Background service + file watcher
└── plugins/             # Plugin loader + built-ins
```

### Building the desktop app

```bash
pip install pyinstaller
pyinstaller desksearch-backend.spec

cd electron && npm install && npm run dist:mac   # or dist:win / dist:linux
```

---

## 📄 License

[MIT](LICENSE) © [Shuai Wang](https://github.com/wshuai190)

---

<p align="center">
  Built by <a href="https://wshuai190.github.io/">Shuai Wang</a>
</p>
