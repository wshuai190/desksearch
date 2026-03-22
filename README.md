<p align="center">
  <img src="docs/logo.png" alt="DeskSearch" width="64" />
  <br />
  <strong style="font-size: 1.5em;">DeskSearch</strong>
</p>

<p align="center">
  <strong>Search your files by meaning, not just keywords. 100% local, zero cloud.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/desksearch/"><img src="https://img.shields.io/pypi/v/desksearch?color=%2334D058&label=pypi" alt="PyPI version" /></a>
  <a href="https://github.com/wshuai190/desksearch/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT" /></a>
</p>

<p align="center">
  <img src="docs/screenshot.png" alt="DeskSearch Demo" width="720" />
</p>

---

## What is DeskSearch?

A private search engine for your local files. It combines keyword matching (BM25) with semantic search (dense vectors) so you can find files by what they *mean*, not just what they say — and nothing ever leaves your machine.

## Install

### Desktop App (recommended)

Download the latest release for your platform:

- **macOS** — `.dmg` (Apple Silicon)
- **Windows** — `.exe` installer
- **Linux** — `.AppImage`

👉 **[Download from Releases](https://github.com/wshuai190/desksearch/releases)**

Just open the app — no Python or terminal needed. It handles everything automatically.

### pip (for CLI / developer use)

```bash
pip install desksearch
desksearch
```

On first run, the setup wizard detects your document folders, indexes them, and opens a web UI at `localhost:3777`.

## Features

- **Desktop app** — standalone app with system tray, global hotkey (`Cmd+Shift+Space` / `Ctrl+Shift+Space`), and built-in folder browser
- **Hybrid search** — BM25 (via [tantivy](https://github.com/quickwit-oss/tantivy)) + dense retrieval (FAISS), merged with Reciprocal Rank Fusion
- **Fully private** — everything runs locally. No cloud, no API keys, no data leaves your machine
- **Fast** — keyword search in <10ms, semantic search in <200ms
- **30+ file formats** — PDF, DOCX, Markdown, HTML, Jupyter notebooks, source code, CSV, LaTeX, and more
- **Web UI** — clean dark-mode interface with folder browser, file explorer, and real-time indexing
- **CLI** — search, index, and manage everything from the terminal
- **Background daemon** — watches folders for changes and re-indexes automatically
- **Plugins** — extend with custom parsers, rerankers, or data connectors

## How It Works

```
  Your Files (PDF, DOCX, Markdown, Code, ...)
                    │
                    ▼
        ┌───────────────────────┐
        │   Parse → Chunk → Embed  │
        └─────┬───────────┬─────┘
              │           │
              ▼           ▼
        ┌─────────┐ ┌──────────┐
        │  BM25   │ │  Dense   │
        │(tantivy)│ │ (FAISS)  │
        └────┬────┘ └────┬─────┘
             │           │
             └─────┬─────┘
                   ▼
          Reciprocal Rank Fusion
                   │
                   ▼
          Ranked Results + Snippets
```

1. **Parse** — extract text from 30+ formats
2. **Chunk** — split into overlapping passages (512 chars, 64 overlap)
3. **Embed** — generate 384-dim vectors with `all-MiniLM-L6-v2` (runs locally)
4. **Search** — query both indexes in parallel, fuse results with RRF

## CLI Usage

```bash
desksearch                          # Start web UI (setup wizard on first run)
desksearch search "your query"      # Search from terminal
desksearch search "ML papers" -n 5  # Limit results
desksearch index ~/Documents        # Index a folder
desksearch status                   # Show index stats
desksearch daemon start             # Run in background with file watcher
desksearch config                   # View/edit configuration
```

## Configuration

Config lives at `~/.desksearch/config.json`:

| Setting | Default | Description |
|---------|---------|-------------|
| `index_paths` | `~/Documents, ~/Desktop` | Folders to index |
| `embedding_model` | `all-MiniLM-L6-v2` | Embedding model |
| `chunk_size` | `512` | Characters per chunk |
| `port` | `3777` | Web UI port |
| `max_file_size_mb` | `50` | Skip files larger than this |

## Plugins

Three extension points: **parsers** (new file formats), **search** (rerankers), and **connectors** (external data sources).

Drop a `.py` file into `~/.desksearch/plugins/`:

```python
from desksearch.plugins.base import BaseParserPlugin
from pathlib import Path

class EpubParser(BaseParserPlugin):
    name = "epub-parser"
    extensions = [".epub"]

    def parse(self, file_path: Path) -> str:
        ...
        return text
```

## Performance

Tested on MacBook Pro M1, 10,000 files (~2GB):

| Metric | Value |
|--------|-------|
| BM25 search | <10ms |
| Semantic search | <200ms |
| Indexing | ~500 files/min |
| Memory (idle) | ~80MB |
| Cold start | ~1.5s |

## Building from Source

### Desktop App

Requires Python 3.10+ and Node.js 18+.

```bash
# 1. Install Python dependencies
pip install -e ".[dev]"

# 2. Bundle the backend
pip install pyinstaller
pyinstaller desksearch.spec  # or see scripts/build-app.sh

# 3. Build the Electron app
cd electron && npm install && npm run dist:mac  # or dist:win / dist:linux
```

### Development

```bash
pip install -e ".[dev]"
pytest

# Frontend dev (hot reload)
cd src/ui && npm install && npm run dev
```

## License

[MIT](LICENSE)

---

<p align="center">
  Built by <a href="https://github.com/wshuai190">Shuai Wang</a>
</p>
