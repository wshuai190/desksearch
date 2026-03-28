# Writing DeskSearch Plugins

DeskSearch has a plugin system that lets you add custom file parsers, search rerankers, and data source connectors. Plugins can be installed via `pip` or dropped into `~/.desksearch/plugins/`.

## Plugin Types

| Type | Base Class | Purpose |
|------|-----------|---------|
| Parser | `BaseParserPlugin` | Parse new file formats (`.epub`, `.pptx`, …) |
| Search | `BaseSearchPlugin` | Rerank or filter search results |
| Connector | `BaseConnectorPlugin` | Pull documents from external sources (Gmail, Slack, Notion, …) |

## Quick Start: A Parser Plugin

```python
# desksearch_epub/__init__.py
from pathlib import Path
from desksearch.plugins.base import BaseParserPlugin


class EpubParser(BaseParserPlugin):
    name = "epub-parser"
    version = "0.1.0"
    author = "Your Name"
    description = "Parse .epub ebook files"
    extensions = [".epub"]

    def parse(self, file_path: Path) -> str:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup

        book = epub.read_epub(str(file_path))
        texts = []
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            soup = BeautifulSoup(item.get_content(), "html.parser")
            texts.append(soup.get_text())
        return "\n\n".join(texts)
```

## Quick Start: A Connector Plugin

```python
from desksearch.plugins.base import BaseConnectorPlugin, Document


class NotionConnector(BaseConnectorPlugin):
    name = "notion-connector"
    version = "0.1.0"
    author = "Your Name"
    description = "Index pages from a Notion workspace"

    def setup(self, config=None):
        config = config or {}
        self.api_key = config.get("api_key", "")

    def fetch(self) -> list[Document]:
        # Use the Notion API to pull pages
        pages = self._query_notion()
        return [
            Document(
                id=f"notion:{p['id']}",
                title=p["title"],
                content=p["content"],
                source="notion",
            )
            for p in pages
        ]

    def sync(self) -> list[Document]:
        # Only fetch pages modified since last sync
        return self.fetch()

    def _query_notion(self):
        ...  # your Notion API logic
```

## Making It pip-Installable

Add an entry point in your `pyproject.toml`:

```toml
[project]
name = "desksearch-notion-connector"
version = "0.1.0"
dependencies = ["desksearch"]

[project.entry-points."desksearch.plugins"]
notion-connector = "desksearch_notion:NotionConnector"
```

Then users simply run:

```bash
pip install desksearch-notion-connector
```

DeskSearch discovers the plugin automatically on next startup.

## Local Development Plugins

Drop a `.py` file into `~/.desksearch/plugins/` and it will be picked up automatically. The file must define at least one class that inherits from a `Base*Plugin`.

## Configuration

Per-plugin settings go in the DeskSearch config file (`~/.desksearch/config.json`):

```json
{
  "enabled_plugins": ["notion-connector", "epub-parser"],
  "plugin_config": {
    "notion-connector": {
      "api_key": "secret_..."
    },
    "email-connector": {
      "directories": ["~/Mail"]
    }
  }
}
```

If `enabled_plugins` is empty, all discovered plugins are loaded. Set it to a list of names to restrict which plugins are active.

## Plugin Lifecycle

1. **Discovery** — `entry_points` and `~/.desksearch/plugins/` are scanned.
2. **Instantiation** — Each plugin class is instantiated with no arguments.
3. **Setup** — `plugin.setup(config)` is called with per-plugin config (if any).
4. **Use** — Parsers are called during indexing; connectors during sync; search plugins during query.
5. **Teardown** — `plugin.teardown()` is called on shutdown.

If any step fails, the plugin is skipped and the error is logged — a bad plugin never crashes DeskSearch.
