# DeskSearch 🔍

**Search your files by meaning. Faster than Spotlight. 100% private.**

<p>
  <a href="https://pypi.org/project/desksearch/"><img src="https://img.shields.io/pypi/v/desksearch?color=%2334D058&label=pypi" /></a>
  <a href="https://github.com/wshuai190/desksearch/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" /></a>
  <a href="https://github.com/wshuai190/desksearch/actions"><img src="https://img.shields.io/github/actions/workflow/status/wshuai190/desksearch/ci.yml?label=tests" /></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" />
</p>

DeskSearch is a local semantic search engine that understands what you're looking for — not just the words you type. It indexes your documents, code, and emails in seconds and finds results in under 2ms. Everything runs on your machine. Nothing is ever sent to the cloud.

<p>
  <img src="docs/screenshot.png" alt="DeskSearch Demo" width="720" />
</p>

---

## Key Features

| | Feature | Description |
|---|---|---|
| 🧠 | **Semantic search** | Understands meaning, not just keywords — finds "quarterly revenue" when you search "Q3 earnings" |
| ⚡ | **<2ms search latency** | Hybrid BM25 + vector search with reciprocal rank fusion |
| 🔒 | **100% private** | Runs entirely on your machine — zero cloud, zero telemetry |
| 📊 | **2D Matryoshka embeddings** | Starbucks model with 3 speed tiers (fast / regular / pro) |
| 📁 | **Auto-indexes folders** | Documents, Desktop, Downloads — or any folder you choose |
| 👁️ | **File watcher** | Instant re-index when files change |
| 🎨 | **Beautiful web UI** | Dark mode, live search, file preview, analytics dashboard |
| 🔌 | **Extensible connectors** | Built-in email, bookmarks, clipboard — or write your own |
| ⌨️ | **Alfred/Raycast integration** | Search from your launcher |
| 📱 | **PWA support** | Pin to your dock as a standalone app |

---

## Performance

Benchmarked on Apple Silicon with 50K documents and 64-dimensional embeddings (regular tier):

| Metric | Value |
|---|---|
| Search latency p50 | **0.83 ms** |
| Search latency p95 | **0.90 ms** |
| FAISS raw search | **0.08 ms** |
| Queries/sec | **1,193** |
| Embedding model | Starbucks 2D Matryoshka (64d) |
| Index size per 1K docs | ~3 MB |
| Frontend bundle | ~92 KB gzip |

---

## Quick Start

```bash
pip install desksearch

desksearch

# Opens http://localhost:3777 — that's it.
```

On first run, DeskSearch walks you through an onboarding wizard to pick folders and a speed tier. After that, `desksearch` starts the server and file watcher automatically.

---

## DeskSearch vs. Alternatives

| | DeskSearch | Spotlight | Everything | Alfred |
|---|---|---|---|---|
| **Search type** | Semantic + keyword | Keyword | Filename only | Keyword |
| **Understands meaning** | Yes | No | No | No |
| **Privacy** | 100% local | Local (with Siri opt-in) | Local | Local |
| **Search latency** | ~1 ms | ~50 ms | ~1 ms | ~50 ms |
| **File content search** | Yes (30+ formats) | Limited | No | Via plugins |
| **Extensible** | Plugins + API | No | No | Workflows |
| **Code-aware** | Yes (20+ languages) | Minimal | No | No |
| **Open source** | Yes (MIT) | No | No | No |

---

## Architecture

DeskSearch uses **hybrid retrieval** — every query runs in parallel against a [Tantivy](https://github.com/quickwit-oss/tantivy) BM25 index (keyword matching) and a FAISS dense vector index (semantic similarity). Results are merged via **Reciprocal Rank Fusion (RRF)** with a tunable alpha parameter, then boosted by filename relevance and recency. Embeddings come from the **Starbucks 2D Matryoshka** model, which supports layer and dimension truncation: you choose a speed tier (`fast` = 2 layers/32d, `regular` = 4 layers/64d, `pro` = 6 layers/128d) and DeskSearch loads only the layers you need. Inference runs on ONNX Runtime for 3-5x speedup over PyTorch. The indexing pipeline parses files in parallel (6 workers), chunks text at sentence boundaries, and embeds in batches of 256 for maximum throughput.

```
Your Files (PDF, DOCX, Markdown, Code, ...)
              │
              ▼  Parse → Chunk → Embed
   ┌──────────────────────────────────────┐
   │   30+ parsers → 512-char chunks      │
   │   → Starbucks 2D Matryoshka (ONNX)   │
   └───────────┬──────────────────────────┘
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

---

## CLI

```bash
# Search from the terminal
desksearch search "machine learning papers"
desksearch search "budget spreadsheet" --type xlsx --json

# Index specific paths
desksearch index ~/Projects ~/Research

# Check index health
desksearch status
desksearch stats          # detailed breakdown
desksearch doctor         # full health check

# Manage watched folders
desksearch folders list
desksearch folders add ~/Notes
desksearch folders remove ~/Old

# Configuration
desksearch config show
desksearch config set search_speed pro

# Background daemon
desksearch daemon start
desksearch daemon install  # auto-start on login (macOS LaunchAgent)
desksearch daemon status
desksearch daemon logs --follow

# Benchmarking
desksearch benchmark --files 1000
```

All commands support `--json` for scripting.

---

## API

DeskSearch exposes a REST API on `localhost:3777`:

```bash
# Search
curl "http://localhost:3777/api/search?q=quarterly+revenue&limit=5"

# Index a folder
curl -X POST "http://localhost:3777/api/index" \
  -H "Content-Type: application/json" \
  -d '{"paths": ["~/Research"]}'

# Index status
curl "http://localhost:3777/api/status"

# List indexed files
curl "http://localhost:3777/api/files?limit=20&type=pdf"

# Find duplicates
curl "http://localhost:3777/api/duplicates"

# Health check
curl "http://localhost:3777/api/health"
```

### Python SDK

```python
from desksearch import DeskSearch

with DeskSearch() as ds:
    results = ds.search("quarterly revenue", limit=5)
    for r in results:
        print(f"{r.rank}. {r.filename} ({r.score:.3f})")
        print(f"   {r.snippet}\n")
```

---

## Configuration

Config lives at `~/.desksearch/config.json`. Edit with `desksearch config set KEY VALUE`.

### Speed Tiers

| Tier | Layers | Dimensions | Use case |
|---|---|---|---|
| `fast` | 2 | 32 | Large corpora, older hardware |
| `regular` | 4 | 64 | **Default** — balanced speed and quality |
| `pro` | 6 | 128 | Best accuracy, more RAM |

```bash
desksearch config set search_speed pro
```

### Other Settings

| Setting | Default | Description |
|---|---|---|
| `port` | `3777` | API server port |
| `index_paths` | `~/Documents, ~/Desktop, ~/Downloads` | Folders to watch |
| `embedding_model` | `ielabgroup/Starbucks-msmarco` | 2D Matryoshka model |
| `chunk_size` | `512` | Characters per chunk |
| `chunk_overlap` | `64` | Overlap between chunks |
| `max_file_size_mb` | `50` | Skip files larger than this |
| `api_key` | `null` | Optional bearer token for API auth |

### Supported File Types

Documents (PDF, DOCX, PPTX, XLSX, EPUB, RTF, LaTeX), code (Python, JS/TS, Java, C/C++, Go, Rust, Ruby, Swift, and more), web (HTML, JSON, YAML, Markdown, CSV), notebooks (Jupyter), email (.eml, .mbox), and archives (ZIP, TAR, GZ).

---

## Plugins

DeskSearch supports three plugin types:

- **Parsers** — add support for new file formats
- **Search plugins** — rerank or filter results
- **Connectors** — pull documents from external sources (email, bookmarks, clipboard)

Drop a `.py` file in `~/.desksearch/plugins/` or install via pip (`entry_points["desksearch.plugins"]`).

Built-in connectors: email indexer, browser bookmarks, clipboard monitor.

---

## Contributing

Contributions are welcome! DeskSearch is MIT-licensed.

```bash
git clone https://github.com/wshuai190/desksearch.git
cd desksearch
pip install -e ".[dev]"
pytest
```

- **Tests**: `pytest` (237 tests)
- **Benchmarks**: `desksearch benchmark`

Please open an issue before submitting large changes.

---

## License

[MIT](LICENSE) © [Shuai Wang](https://github.com/wshuai190)
