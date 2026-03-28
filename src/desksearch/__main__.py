"""CLI entry point for DeskSearch.

Usage:
    desksearch                         # First run → onboarding; otherwise → serve
    desksearch setup                   # Re-run the onboarding wizard
    desksearch search "query"          # Search from terminal
    desksearch index PATH [PATH ...]   # Index specific paths
    desksearch status                  # Show index stats
    desksearch folders list            # List watched folders
    desksearch folders add PATH        # Add folder to watch list
    desksearch folders remove PATH     # Remove folder from watch list
    desksearch config show             # View current configuration
    desksearch config set KEY VALUE    # Update a config value
    desksearch doctor                  # Check health of all components
    desksearch serve [--host HOST] [--port PORT]
    desksearch daemon start|stop|status|install|uninstall|logs
    desksearch benchmark               # Benchmark indexing throughput
"""
import json as _json
import sys
import time
import webbrowser
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from desksearch.config import Config

import os as _os
_os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# Prevent OpenMP crash when both FAISS and ONNX Runtime link libomp (macOS)
_os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

console = Console()
err_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_json(data: object) -> None:
    """Print data as JSON to stdout."""
    click.echo(_json.dumps(data, indent=2, default=str))


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------

class _DefaultGroup(click.Group):
    """Click group that runs onboarding or serve when invoked with no subcommand.

    Note: ``ctx.invoked_subcommand`` is not yet set when ``invoke()`` is
    called — Click populates it *inside* ``super().invoke()``.  We must
    check ``ctx._protected_args`` (which holds the subcommand token after
    ``parse_args``) to decide whether a real subcommand was requested.
    """

    def invoke(self, ctx: click.Context) -> None:
        # _protected_args is non-empty when a subcommand was parsed
        has_subcommand = bool(ctx._protected_args or ctx.args)
        if not has_subcommand:
            from desksearch.onboarding import is_first_run

            if is_first_run():
                ctx.invoke(setup)
            else:
                ctx.invoke(serve)
        else:
            super().invoke(ctx)


@click.group(cls=_DefaultGroup, invoke_without_command=True)
@click.version_option(package_name="desksearch")
def cli() -> None:
    """DeskSearch — private semantic search for your local files.

    \b
    Run without arguments to start the web UI (setup wizard on first run).

    \b
    Common commands:
      desksearch search "machine learning papers"
      desksearch index ~/Documents
      desksearch status
      desksearch doctor
    """


# ---------------------------------------------------------------------------
# setup (onboarding)
# ---------------------------------------------------------------------------

@cli.command(epilog="""
\b
Examples:
  desksearch setup          # Interactive first-time setup wizard
""")
def setup() -> None:
    """Run (or re-run) the first-time setup wizard."""
    from desksearch.onboarding import run_onboarding_wizard
    run_onboarding_wizard()


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

@cli.command(epilog="""
\b
Examples:
  desksearch search "quarterly report"
  desksearch search "machine learning" -n 5
  desksearch search "budget" --type pdf
  desksearch search "todo items" --json
""")
@click.argument("query")
@click.option("--limit", "-n", default=10, show_default=True, help="Maximum results to show")
@click.option("--type", "file_type", default=None, help="Filter by file extension (e.g. pdf, md, py)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON for scripting")
def search(query: str, limit: int, file_type: str | None, as_json: bool) -> None:
    """Search your indexed files from the terminal.

    QUERY is the search string — use natural language or keywords.

    \b
    Results show filename, path, relevance score, and a text snippet.
    Use --json to get machine-readable output for scripts.
    """
    from desksearch.core.search import HybridSearchEngine
    from desksearch.indexer.embedder import Embedder
    from desksearch.indexer.store import MetadataStore

    config = Config.load()
    store = MetadataStore(config.data_dir / "metadata.db")

    if store.document_count() == 0:
        msg = "No files indexed yet. Run 'desksearch index <path>' first."
        if as_json:
            _print_json({"error": msg, "results": []})
        else:
            console.print(f"[yellow]{msg}[/yellow]")
        store.close()
        return

    config.resolve_starbucks_tier()
    embedder = Embedder(config.embedding_model, embedding_dim=config.embedding_dim, embedding_layers=config.embedding_layers)
    engine = HybridSearchEngine(config)

    from desksearch.api.server import _warm_search_engine
    # FIX: _warm_search_engine takes (engine, store, config), not 4 args
    _warm_search_engine(engine, store, config)

    query_embedding = embedder.embed_query(query)
    raw_results = engine.search_sync(query, query_embedding, top_k=limit * 2)

    output_results = []
    for r in raw_results:
        try:
            chunk_id = int(r.doc_id)
        except (ValueError, TypeError):
            continue

        chunk = store.get_chunk_by_id(chunk_id)
        if chunk is None:
            continue

        doc = store.get_document_by_id(chunk.doc_id)
        if doc is None:
            continue

        ext = doc.extension.lstrip(".")
        if file_type and ext != file_type:
            continue

        snippet = r.snippets[0].text if r.snippets else chunk.text[:200]
        output_results.append({
            "rank": len(output_results) + 1,
            "filename": doc.filename,
            "path": str(doc.path),
            "extension": ext,
            "score": round(r.score, 6),
            "snippet": snippet,
        })

        if len(output_results) >= limit:
            break

    store.close()

    if as_json:
        _print_json({
            "query": query,
            "total": len(output_results),
            "results": output_results,
        })
        return

    # Pretty output
    console.print(f'\n[bold]🔍 Results for:[/bold] [cyan]"{query}"[/cyan]\n')

    if not output_results:
        console.print("[yellow]No results found.[/yellow]")
        return

    for item in output_results:
        console.print(
            f"[bold cyan]{item['rank']}.[/bold cyan] "
            f"[bold]{item['filename']}[/bold]  "
            f"[dim]{item['extension']}[/dim]  "
            f"[dim]score={item['score']:.4f}[/dim]"
        )
        console.print(f"   [blue dim]{item['path']}[/blue dim]")
        # Wrap snippet at 100 chars for readability
        snippet = item["snippet"].replace("\n", " ").strip()
        if len(snippet) > 200:
            snippet = snippet[:197] + "…"
        console.print(f"   {snippet}\n")

    console.print(f"[dim]Showing {len(output_results)} result(s)[/dim]\n")


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------

@cli.command(epilog="""
\b
Examples:
  desksearch index ~/Documents
  desksearch index ~/Papers ~/Notes ~/Desktop
  desksearch index ./project --json
""")
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON for scripting")
def index(paths: tuple[str, ...], as_json: bool) -> None:
    """Index files or directories.

    Parses, chunks, and embeds all supported files under each PATH.
    Already-indexed unchanged files are skipped automatically.
    """
    from desksearch.core.search import HybridSearchEngine
    from desksearch.indexer.pipeline import IndexingPipeline, StatusType

    config = Config.load()
    resolved = [Path(p).resolve() for p in paths]

    if not as_json:
        console.print(f"[bold]Indexing {len(resolved)} path(s)...[/bold]")
        for p in resolved:
            console.print(f"  • {p}")
        console.print()

    engine = HybridSearchEngine(config)
    pipeline = IndexingPipeline(config, search_engine=engine)

    stats = {"indexed": 0, "errors": 0, "skipped": 0, "files": []}

    try:
        for path in resolved:
            gen = pipeline.index_directory(path) if path.is_dir() else pipeline.index_file(path)
            try:
                while True:
                    status = next(gen)
                    if status.status == StatusType.COMPLETE and status.file:
                        stats["indexed"] += 1
                        entry = {"file": str(status.file), "status": "ok", "message": status.message}
                        stats["files"].append(entry)
                        if not as_json:
                            console.print(f"  [green]✓[/green] {Path(status.file).name}  [dim]{status.message}[/dim]")
                    elif status.status == StatusType.ERROR:
                        stats["errors"] += 1
                        entry = {"file": str(status.file or ""), "status": "error", "message": status.message}
                        stats["files"].append(entry)
                        if not as_json:
                            console.print(f"  [red]✗[/red] {status.file}: {status.message}")
                    elif status.status == StatusType.SKIPPED:
                        stats["skipped"] += 1
                        if not as_json:
                            console.print(f"  [dim]– {Path(status.file).name} (skipped)[/dim]")
                    elif status.status == StatusType.DISCOVERY:
                        if not as_json:
                            console.print(f"  [blue]{status.message}[/blue]")
            except StopIteration:
                pass

        total_docs = pipeline.store.document_count()
        total_chunks = pipeline.store.chunk_count()
        stats["total_documents"] = total_docs
        stats["total_chunks"] = total_chunks

    finally:
        pipeline.close()

    if as_json:
        _print_json(stats)
    else:
        color = "green" if stats["errors"] == 0 else "yellow"
        console.print(
            f"\n[bold {color}]Done:[/bold {color}] "
            f"{stats['indexed']} indexed, "
            f"{stats['skipped']} skipped, "
            f"{stats['errors']} errors"
        )
        console.print(
            f"Index now contains [bold]{total_docs}[/bold] documents "
            f"([bold]{total_chunks}[/bold] chunks)"
        )


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@cli.command(epilog="""
\b
Examples:
  desksearch status
  desksearch status --json
""")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON for scripting")
def status(as_json: bool) -> None:
    """Show index statistics and configuration summary.

    Displays document count, chunk count, disk usage, watched folders,
    and the current embedding model.
    """
    from desksearch.indexer.store import MetadataStore
    import shutil

    config = Config.load()
    store = MetadataStore(config.data_dir / "metadata.db")

    doc_count = store.document_count()
    chunk_count = store.chunk_count()
    store.close()

    # Disk usage breakdown
    total_bytes = 0
    component_sizes: dict[str, float] = {}
    if config.data_dir.exists():
        for component in ("dense", "bm25", "metadata.db"):
            comp_path = config.data_dir / component
            if comp_path.is_dir():
                sz = sum(f.stat().st_size for f in comp_path.rglob("*") if f.is_file())
            elif comp_path.is_file():
                sz = comp_path.stat().st_size
            else:
                sz = 0
            component_sizes[component] = sz
            total_bytes += sz

    total_mb = total_bytes / (1024 * 1024)

    # Last indexed time (mtime of metadata.db)
    db_path = config.data_dir / "metadata.db"
    last_indexed = None
    if db_path.exists():
        import datetime
        last_indexed = datetime.datetime.fromtimestamp(db_path.stat().st_mtime).isoformat(timespec="seconds")

    data = {
        "data_dir": str(config.data_dir),
        "watched_folders": [str(p) for p in config.index_paths],
        "embedding_model": config.embedding_model,
        "chunk_size": config.chunk_size,
        "chunk_overlap": config.chunk_overlap,
        "documents": doc_count,
        "chunks": chunk_count,
        "disk_usage_mb": round(total_mb, 2),
        "last_indexed": last_indexed,
        "server": f"http://{config.host}:{config.port}",
    }

    if as_json:
        _print_json(data)
        return

    table = Table(title="[bold]DeskSearch Status[/bold]", box=box.ROUNDED, show_header=False)
    table.add_column("Key", style="bold cyan", width=22)
    table.add_column("Value")

    table.add_row("Documents", f"[bold]{doc_count:,}[/bold]")
    table.add_row("Chunks", f"[bold]{chunk_count:,}[/bold]")
    table.add_row("Disk usage", f"[bold]{total_mb:.1f} MB[/bold]")
    table.add_row("Last indexed", last_indexed or "[dim]never[/dim]")
    table.add_row("Server", f"[link]http://{config.host}:{config.port}[/link]")
    table.add_row("Data dir", str(config.data_dir))
    table.add_row("Embedding model", config.embedding_model)
    table.add_row(
        "Watched folders",
        "\n".join(str(p) for p in config.index_paths) or "[dim]none[/dim]",
    )

    console.print(table)


# ---------------------------------------------------------------------------
# stats (detailed)
# ---------------------------------------------------------------------------

@cli.command(epilog="""
\b
Examples:
  desksearch stats
  desksearch stats --json
""")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON for scripting")
def stats(as_json: bool) -> None:
    """Show detailed storage and performance statistics.

    Breaks down disk usage by component (FAISS dense index, BM25, SQLite),
    reports FAISS index type, fragmentation, and cache metrics.
    """
    from desksearch.indexer.store import MetadataStore

    config = Config.load()
    store = MetadataStore(config.data_dir / "metadata.db")

    doc_count = store.document_count()
    chunk_count = store.chunk_count()
    db_stats = store.disk_stats()
    store.close()

    db_size_mb = db_stats["db_size_bytes"] / (1024 * 1024)
    frag_pct = db_stats["frag_ratio"] * 100

    faiss_dir = config.data_dir / "dense"
    faiss_size_bytes = sum(
        f.stat().st_size for f in faiss_dir.rglob("*") if f.is_file()
    ) if faiss_dir.exists() else 0
    faiss_size_mb = faiss_size_bytes / (1024 * 1024)

    bm25_dir = config.data_dir / "bm25"
    bm25_size_bytes = sum(
        f.stat().st_size for f in bm25_dir.rglob("*") if f.is_file()
    ) if bm25_dir.exists() else 0
    bm25_size_mb = bm25_size_bytes / (1024 * 1024)

    total_bytes = db_stats["db_size_bytes"] + faiss_size_bytes + bm25_size_bytes
    if config.data_dir.exists():
        for f in config.data_dir.rglob("*"):
            if f.is_file() and not any(
                f.is_relative_to(d) for d in (faiss_dir, bm25_dir) if d.exists()
            ) and f != (config.data_dir / "metadata.db"):
                total_bytes += f.stat().st_size
    total_mb = total_bytes / (1024 * 1024)

    try:
        from desksearch.core.dense import DenseIndex
        idx = DenseIndex(config.data_dir, use_mmap=True)
        idx_type = idx.index_type
        idx_vecs = idx.doc_count
        soft_del = len(idx._soft_deleted)
    except Exception:
        idx_type = "unknown"
        idx_vecs = 0
        soft_del = 0

    avg_chunk_bytes = (db_stats["db_size_bytes"] / chunk_count) if chunk_count else 0

    data = {
        "documents": doc_count,
        "chunks": chunk_count,
        "avg_chunk_bytes": round(avg_chunk_bytes, 1),
        "faiss": {
            "index_type": idx_type,
            "vectors": idx_vecs,
            "soft_deleted": soft_del,
            "size_mb": round(faiss_size_mb, 2),
        },
        "bm25": {"size_mb": round(bm25_size_mb, 2)},
        "sqlite": {
            "size_mb": round(db_size_mb, 2),
            "fragmentation_pct": round(frag_pct, 1),
        },
        "total_mb": round(total_mb, 2),
        "data_dir": str(config.data_dir),
    }

    if as_json:
        _print_json(data)
        return

    table = Table(title="[bold]DeskSearch Stats[/bold]", box=box.ROUNDED, show_header=True)
    table.add_column("Category", style="bold cyan")
    table.add_column("Metric")
    table.add_column("Value", justify="right")

    table.add_row("Index", "Documents", f"{doc_count:,}")
    table.add_row("", "Chunks", f"{chunk_count:,}")
    table.add_row("", "Avg chunk size", f"{avg_chunk_bytes:.0f} B")
    table.add_row("FAISS", "Index type", idx_type)
    table.add_row("", "Vectors", str(idx_vecs))
    if soft_del:
        table.add_row("", "Soft-deleted (GC pending)", str(soft_del))
    table.add_row("", "Size on disk", f"{faiss_size_mb:.2f} MB")
    table.add_row("BM25", "Size on disk", f"{bm25_size_mb:.2f} MB")
    table.add_row("SQLite", "DB size", f"{db_size_mb:.2f} MB")
    table.add_row("", "Fragmentation", f"{frag_pct:.1f}%")
    table.add_row("Total", "Disk usage", f"[bold]{total_mb:.2f} MB[/bold]")
    table.add_row("", "Data dir", str(config.data_dir))

    console.print(table)

    if frag_pct >= 10:
        console.print(
            f"[yellow]⚠  SQLite fragmented ({frag_pct:.0f}%). Run VACUUM to reclaim space.[/yellow]"
        )
    if soft_del:
        console.print(
            f"[yellow]⚠  {soft_del} soft-deleted FAISS vector(s) pending GC. "
            "Restart DeskSearch to compact.[/yellow]"
        )


# ---------------------------------------------------------------------------
# folders group
# ---------------------------------------------------------------------------

@cli.group(epilog="""
\b
Examples:
  desksearch folders list
  desksearch folders add ~/Research
  desksearch folders remove ~/Downloads
""")
def folders() -> None:
    """Manage indexed folders (list, add, remove).

    Changes take effect immediately — added folders are queued for
    indexing and removed folders are no longer watched.
    """


@folders.command("list", epilog="""
\b
Examples:
  desksearch folders list
  desksearch folders list --json
""")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON for scripting")
def folders_list(as_json: bool) -> None:
    """List all watched folders."""
    config = Config.load()
    paths = [str(p) for p in config.index_paths]

    if as_json:
        _print_json({"folders": paths, "count": len(paths)})
        return

    if not paths:
        console.print("[dim]No folders configured. Use 'desksearch folders add <path>'.[/dim]")
        return

    console.print(f"\n[bold]Watched folders ({len(paths)}):[/bold]\n")
    for p in paths:
        exists = Path(p).exists()
        icon = "📁" if exists else "❌"
        note = "" if exists else "  [red dim](not found)[/red dim]"
        console.print(f"  {icon}  {p}{note}")
    console.print()


@folders.command("add", epilog="""
\b
Examples:
  desksearch folders add ~/Research
  desksearch folders add ~/Papers --json
""")
@click.argument("folder", type=click.Path())
@click.option("--json", "as_json", is_flag=True, help="Output as JSON for scripting")
def folders_add(folder: str, as_json: bool) -> None:
    """Add a folder to the watch list and index it.

    FOLDER will be recursively scanned for supported file types and
    added to the auto-watch list for future changes.
    """
    from desksearch.onboarding import add_folder
    resolved = str(Path(folder).expanduser().resolve())
    add_folder(folder)

    if as_json:
        config = Config.load()
        _print_json({"added": resolved, "folders": [str(p) for p in config.index_paths]})
    else:
        console.print(f"[green]✓[/green] Added folder: [bold]{resolved}[/bold]")


@folders.command("remove", epilog="""
\b
Examples:
  desksearch folders remove ~/Downloads
  desksearch folders remove ~/Downloads --json
""")
@click.argument("folder", type=click.Path())
@click.option("--json", "as_json", is_flag=True, help="Output as JSON for scripting")
def folders_remove(folder: str, as_json: bool) -> None:
    """Remove a folder from the watch list.

    FOLDER will no longer be watched or indexed. Existing index entries
    for that folder remain until you re-index or clear the database.
    """
    from desksearch.onboarding import remove_folder
    resolved = str(Path(folder).expanduser().resolve())
    remove_folder(folder)

    if as_json:
        config = Config.load()
        _print_json({"removed": resolved, "folders": [str(p) for p in config.index_paths]})
    else:
        console.print(f"[green]✓[/green] Removed folder: [bold]{resolved}[/bold]")


# Keep top-level add/remove for backward compatibility
@cli.command(hidden=True)
@click.argument("folder", type=click.Path())
def add(folder: str) -> None:
    """Add a folder to the watch list and index it. (Use 'folders add' instead.)"""
    from desksearch.onboarding import add_folder
    add_folder(folder)


@cli.command(hidden=True)
@click.argument("folder", type=click.Path())
def remove(folder: str) -> None:
    """Remove a folder from the watch list. (Use 'folders remove' instead.)"""
    from desksearch.onboarding import remove_folder
    remove_folder(folder)


# ---------------------------------------------------------------------------
# config group
# ---------------------------------------------------------------------------

@cli.group(invoke_without_command=True, epilog="""
\b
Examples:
  desksearch config show
  desksearch config set chunk_size 256
  desksearch config set port 4000
""")
@click.pass_context
def config(ctx: click.Context) -> None:
    """View or modify DeskSearch configuration.

    Sub-commands: show, set

    Config is stored at ~/.desksearch/config.json
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(config_show)


@config.command("show", epilog="""
\b
Examples:
  desksearch config show
  desksearch config show --json
""")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON for scripting")
def config_show(as_json: bool = False) -> None:
    """Display the current configuration."""
    cfg = Config.load()
    data = cfg.model_dump(mode="json")

    if as_json:
        _print_json(data)
        return

    table = Table(title="[bold]DeskSearch Configuration[/bold]", box=box.ROUNDED, show_header=True)
    table.add_column("Key", style="bold cyan")
    table.add_column("Value")
    table.add_column("Description", style="dim")

    field_descriptions = {f: Config.model_fields[f].description or "" for f in Config.model_fields}

    for key, value in data.items():
        desc = field_descriptions.get(key, "")
        table.add_row(key, str(value), desc)

    console.print(table)


# "list" is an alias for "show"
@config.command("list", hidden=True)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON for scripting")
@click.pass_context
def config_list(ctx: click.Context, as_json: bool = False) -> None:
    """List all configuration values (alias for 'show')."""
    ctx.invoke(config_show, as_json=as_json)


@config.command("get", epilog="""
\b
Examples:
  desksearch config get port
  desksearch config get search_speed
  desksearch config get embedding_model --json
""")
@click.argument("key")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON for scripting")
def config_get(key: str, as_json: bool) -> None:
    """Get a single configuration value.

    KEY is the config field name (e.g. port, search_speed).
    """
    cfg = Config.load()
    data = cfg.model_dump(mode="json")

    if key not in data:
        known = ", ".join(sorted(data.keys()))
        err_console.print(f"[red]Unknown config key:[/red] [bold]{key}[/bold]")
        err_console.print(f"[dim]Valid keys: {known}[/dim]")
        sys.exit(1)

    if as_json:
        _print_json({"key": key, "value": data[key]})
    else:
        console.print(f"[bold]{key}[/bold] = [cyan]{data[key]}[/cyan]")


@config.command("set", epilog="""
\b
Examples:
  desksearch config set port 4000
  desksearch config set chunk_size 256
  desksearch config set embedding_model all-MiniLM-L12-v2
  desksearch config set max_file_size_mb 100
""")
@click.argument("key")
@click.argument("value")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON for scripting")
def config_set(key: str, value: str, as_json: bool) -> None:
    """Update a single configuration value.

    KEY is the config field name (e.g. port, chunk_size).
    VALUE is the new value as a string — it will be coerced to the right type.

    \b
    Use 'desksearch config show' to see all available keys.
    """
    cfg = Config.load()
    data = cfg.model_dump()

    if key not in data:
        known = ", ".join(sorted(data.keys()))
        err_console.print(f"[red]Unknown config key:[/red] [bold]{key}[/bold]")
        err_console.print(f"[dim]Valid keys: {known}[/dim]")
        sys.exit(1)

    current = data[key]
    if isinstance(current, bool):
        data[key] = value.lower() in ("true", "1", "yes")
    elif isinstance(current, int):
        try:
            data[key] = int(value)
        except ValueError:
            err_console.print(f"[red]Expected integer for {key}, got:[/red] {value}")
            sys.exit(1)
    elif isinstance(current, list):
        data[key] = [v.strip() for v in value.split(",")]
    else:
        data[key] = value

    cfg = Config(**data)
    cfg.save()

    if as_json:
        _print_json({"key": key, "value": data[key], "saved": True})
    else:
        console.print(f"[green]✓[/green] Set [bold]{key}[/bold] = [cyan]{data[key]}[/cyan]")
        console.print(f"[dim]Config saved to {cfg.data_dir / 'config.json'}[/dim]")


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

@cli.command(epilog="""
\b
Examples:
  desksearch doctor
  desksearch doctor --json
""")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON for scripting")
def doctor(as_json: bool) -> None:
    """Check the health of all DeskSearch components.

    Verifies that required Python packages are installed, the data directory
    is accessible, the embedding model can be loaded, and the search indexes
    are readable. Exits with code 1 if any check fails.
    """
    import importlib
    import shutil

    checks: list[dict] = []

    def _check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    # 1. Required packages
    required_packages = [
        ("click", "click"),
        ("rich", "rich"),
        ("faiss", "faiss"),
        ("tantivy", "tantivy"),
        ("pydantic", "pydantic"),
        ("uvicorn", "uvicorn"),
        ("fastapi", "fastapi"),
        ("tokenizers", "tokenizers"),
        ("onnxruntime", "onnxruntime"),
        ("watchdog", "watchdog"),
    ]
    for display_name, mod_name in required_packages:
        try:
            importlib.import_module(mod_name)
            _check(f"Package: {display_name}", True)
        except ImportError as e:
            _check(f"Package: {display_name}", False, str(e))

    # 2. Data directory
    config = Config.load()
    try:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        test_file = config.data_dir / ".doctor_test"
        test_file.write_text("ok")
        test_file.unlink()
        _check("Data directory (read/write)", True, str(config.data_dir))
    except Exception as e:
        _check("Data directory (read/write)", False, str(e))

    # 3. Disk space (warn if <500MB free)
    try:
        usage = shutil.disk_usage(config.data_dir)
        free_gb = usage.free / (1024 ** 3)
        ok = free_gb >= 0.5
        _check("Disk space (≥500 MB free)", ok, f"{free_gb:.1f} GB free")
    except Exception as e:
        _check("Disk space", False, str(e))

    # 4. Embedding model
    try:
        from desksearch.indexer.embedder import Embedder
        config.resolve_starbucks_tier()
        embedder = Embedder(config.embedding_model, embedding_dim=config.embedding_dim, embedding_layers=config.embedding_layers)
        vec = embedder.embed_query("test")
        ok = vec is not None and len(vec) > 0
        tier = config.search_speed
        _check(f"Embedding model ({config.embedding_model}, {tier})", ok, f"dim={len(vec)}")
    except Exception as e:
        _check(f"Embedding model ({config.embedding_model})", False, str(e))

    # 5. Metadata store
    try:
        from desksearch.indexer.store import MetadataStore
        store = MetadataStore(config.data_dir / "metadata.db")
        doc_count = store.document_count()
        chunk_count = store.chunk_count()
        store.close()
        _check("Metadata store (SQLite)", True, f"{doc_count} docs, {chunk_count} chunks")
    except Exception as e:
        _check("Metadata store (SQLite)", False, str(e))

    # 6. BM25 index
    try:
        from desksearch.core.bm25 import BM25Index
        bm25 = BM25Index(config.data_dir)
        _check("BM25 index (tantivy)", True)
    except Exception as e:
        _check("BM25 index (tantivy)", False, str(e))

    # 7. Dense index
    try:
        from desksearch.core.dense import DenseIndex
        dense = DenseIndex(config.data_dir, use_mmap=True)
        _check("Dense index (FAISS)", True, f"type={dense.index_type}, vectors={dense.doc_count}")
    except Exception as e:
        _check("Dense index (FAISS)", False, str(e))

    # 8. Config validation
    issues = config.validate()
    # Filter out port-in-use warnings (server may already be running)
    config_issues = [i for i in issues if "Port" not in i and "port" not in i.lower()]
    _check("Config validation", len(config_issues) == 0,
           "; ".join(config_issues) if config_issues else "OK")

    # Results
    all_ok = all(c["ok"] for c in checks)

    if as_json:
        _print_json({"healthy": all_ok, "checks": checks})
        if not all_ok:
            sys.exit(1)
        return

    console.print("\n[bold]DeskSearch Doctor[/bold]\n")
    for c in checks:
        icon = "[bold green]✓[/bold green]" if c["ok"] else "[bold red]✗[/bold red]"
        detail = f"  [dim]{c['detail']}[/dim]" if c["detail"] else ""
        console.print(f"  {icon}  {c['name']}{detail}")

    console.print()
    if all_ok:
        console.print(Panel(
            "[bold green]All checks passed![/bold green] DeskSearch is healthy.",
            border_style="green",
        ))
    else:
        failed = [c for c in checks if not c["ok"]]
        console.print(Panel(
            f"[bold red]{len(failed)} check(s) failed.[/bold red] "
            "Run 'pip install desksearch[full]' or check the errors above.",
            border_style="red",
        ))
        sys.exit(1)


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------

@cli.command(epilog="""
\b
Examples:
  desksearch serve
  desksearch serve --port 8080
  desksearch serve --host 0.0.0.0 --port 3777 --no-browser
""")
@click.option("--host", default=None, help="Bind host (default: from config)")
@click.option("--port", default=None, type=int, help="Bind port (default: from config)")
@click.option("--no-browser", is_flag=True, help="Don't auto-open the browser on start")
def serve(host: str | None, port: int | None, no_browser: bool) -> None:
    """Start the DeskSearch web server.

    Opens a browser window to the search UI automatically unless
    --no-browser is passed. The server runs in the foreground; press
    Ctrl+C to stop.
    """
    import uvicorn

    from desksearch.api.server import create_app
    from desksearch.indexer.store import MetadataStore

    config = Config.load()
    host = host or config.host
    port = port or config.port

    app = create_app(config)

    store = MetadataStore(config.data_dir / "metadata.db")
    doc_count = store.document_count()
    chunk_count = store.chunk_count()
    store.close()

    url = f"http://{host}:{port}"
    banner = (
        f"[bold cyan]DeskSearch[/bold cyan]\n\n"
        f"  Search URL:  [link]{url}[/link]\n"
        f"  Documents:   [bold]{doc_count:,}[/bold] files indexed\n"
        f"  Chunks:      [bold]{chunk_count:,}[/bold] searchable chunks\n"
        f"  Data dir:    {config.data_dir}\n\n"
        f"  [dim]Press Ctrl+C to stop[/dim]"
    )
    console.print(Panel(banner, title="[bold green]Ready[/bold green]", border_style="green"))

    if not no_browser:
        import threading

        def _open_browser() -> None:
            time.sleep(1.0)
            webbrowser.open(url)

        threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="info")


# ---------------------------------------------------------------------------
# benchmark
# ---------------------------------------------------------------------------

@cli.command(epilog="""
\b
Examples:
  desksearch benchmark
  desksearch benchmark --files 500 --size 16
  desksearch benchmark --dir ~/Documents
  desksearch benchmark --json
""")
@click.option(
    "--dir", "bench_dir", default=None,
    help="Directory to index for benchmark (default: auto-generated temp directory)",
    type=click.Path(),
)
@click.option(
    "--files", "n_files", default=200, show_default=True,
    help="Number of synthetic files to create when using the auto temp directory",
)
@click.option(
    "--size", "file_size_kb", default=8, show_default=True,
    help="Approximate size of each synthetic file in KB",
)
@click.option(
    "--keep", is_flag=True, default=False,
    help="Keep the temp directory after the benchmark (useful for inspection)",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON for scripting")
def benchmark(
    bench_dir: str | None,
    n_files: int,
    file_size_kb: int,
    keep: bool,
    as_json: bool,
) -> None:
    """Benchmark indexing throughput and report performance metrics.

    Creates (or uses) a directory of documents, indexes them from scratch,
    and reports files/sec, chunks/sec, MB/sec, peak memory, and total time.

    Target on an M-series Mac: 100+ files/sec for typical small documents.
    """
    import os
    import shutil
    import tempfile
    import tracemalloc
    import resource

    from desksearch.indexer.pipeline import IndexingPipeline, StatusType

    config = Config.load()

    temp_dir_created = False
    if bench_dir:
        target = Path(bench_dir).resolve()
        if not target.exists():
            err_console.print(f"[red]Directory not found:[/red] {target}")
            sys.exit(1)
        if not as_json:
            console.print(f"[bold]Benchmarking existing directory:[/bold] {target}")
    else:
        target = Path(tempfile.mkdtemp(prefix="desksearch_bench_"))
        temp_dir_created = True
        if not as_json:
            console.print(
                f"[bold]Creating {n_files} synthetic files[/bold] "
                f"(~{file_size_kb} KB each) in [dim]{target}[/dim]"
            )

        import random
        words = (
            "information retrieval natural language processing machine learning "
            "deep learning transformer attention embedding vector semantic search "
            "document indexing chunking tokenization paragraph sentence query "
            "relevant result score ranking model neural network dataset training "
        ).split()

        def _rand_para(rng: random.Random, n_sentences: int = 5) -> str:
            sents = []
            for _ in range(n_sentences):
                n = rng.randint(8, 20)
                sents.append(" ".join(rng.choices(words, k=n)) + ".")
            return " ".join(sents)

        rng = random.Random(42)
        target_bytes = file_size_kb * 1024
        for i in range(n_files):
            ext = rng.choice([".txt", ".md", ".py"])
            fpath = target / f"doc_{i:04d}{ext}"
            parts = []
            total = 0
            while total < target_bytes:
                para = _rand_para(rng)
                parts.append(para)
                total += len(para)
            fpath.write_text("\n\n".join(parts))

        if not as_json:
            console.print(f"  Created {n_files} files in {target}")

    bench_data = Path(tempfile.mkdtemp(prefix="desksearch_bench_data_"))
    bench_config = config.model_copy(update={"data_dir": bench_data})

    tracemalloc.start()
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    pipeline = IndexingPipeline(config=bench_config)
    t_start = time.perf_counter()

    total_files = 0
    total_chunks = 0
    errors = 0

    try:
        gen = pipeline.index_directory(target)
        try:
            while True:
                status = next(gen)
                if status.status == StatusType.COMPLETE and status.file:
                    total_files += 1
                    try:
                        total_chunks += int(status.message.split()[0])
                    except (IndexError, ValueError):
                        pass
                elif status.status == StatusType.ERROR:
                    errors += 1
        except StopIteration:
            pass
    finally:
        pipeline.close()

    elapsed = time.perf_counter() - t_start
    rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    _, peak_traced = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    total_bytes = sum(
        f.stat().st_size for f in target.rglob("*") if f.is_file()
    )
    total_mb = total_bytes / (1024 * 1024)

    files_sec = total_files / elapsed if elapsed > 0 else 0
    chunks_sec = total_chunks / elapsed if elapsed > 0 else 0
    mb_sec = total_mb / elapsed if elapsed > 0 else 0
    peak_mb = peak_traced / (1024 * 1024)

    import platform
    rss_delta = rss_after - rss_before
    if platform.system() == "Darwin":
        rss_delta_mb = rss_delta / (1024 * 1024)
    else:
        rss_delta_mb = rss_delta * 4 / 1024

    cache_stats = pipeline.embedder.chunk_cache_stats

    if as_json:
        _print_json({
            "files_indexed": total_files,
            "errors": errors,
            "total_chunks": total_chunks,
            "total_data_mb": round(total_mb, 2),
            "elapsed_sec": round(elapsed, 2),
            "files_per_sec": round(files_sec, 1),
            "chunks_per_sec": round(chunks_sec, 1),
            "mb_per_sec": round(mb_sec, 2),
            "peak_traced_memory_mb": round(peak_mb, 1),
            "rss_delta_mb": round(rss_delta_mb, 1),
            "cache": cache_stats,
            "target_met": files_sec >= 100,
        })
    else:
        table = Table(title="DeskSearch Indexing Benchmark", show_header=True)
        table.add_column("Metric", style="bold cyan")
        table.add_column("Value", justify="right")

        table.add_row("Files indexed", str(total_files))
        table.add_row("Errors", str(errors))
        table.add_row("Total chunks", str(total_chunks))
        table.add_row("Total data", f"{total_mb:.1f} MB")
        table.add_row("─" * 20, "─" * 15)
        table.add_row("Total time", f"{elapsed:.2f} s")
        table.add_row("Files / sec", f"[bold]{files_sec:.1f}[/bold]")
        table.add_row("Chunks / sec", f"{chunks_sec:.1f}")
        table.add_row("MB / sec", f"{mb_sec:.2f}")
        table.add_row("─" * 20, "─" * 15)
        table.add_row("Peak traced memory", f"{peak_mb:.1f} MB")
        table.add_row("RSS delta", f"{rss_delta_mb:.1f} MB")

        if cache_stats["hits"] + cache_stats["misses"] > 0:
            table.add_row("─" * 20, "─" * 15)
            table.add_row(
                "Chunk cache hit rate",
                f"{cache_stats['hit_rate'] * 100:.1f}% ({cache_stats['hits']} hits)",
            )

        console.print(table)

        if files_sec >= 100:
            console.print(
                f"\n[bold green]✓ Target met![/bold green] "
                f"{files_sec:.0f} files/sec ≥ 100 files/sec"
            )
        else:
            console.print(
                f"\n[yellow]⚠ Below target:[/yellow] "
                f"{files_sec:.0f} files/sec < 100 files/sec. "
                "Check ONNX thread config and batch sizes."
            )

    if temp_dir_created and not keep:
        shutil.rmtree(target, ignore_errors=True)
    shutil.rmtree(bench_data, ignore_errors=True)


# ---------------------------------------------------------------------------
# daemon group
# ---------------------------------------------------------------------------

@cli.group(epilog="""
\b
Examples:
  desksearch daemon start
  desksearch daemon status
  desksearch daemon stop
  desksearch daemon logs --follow
""")
def daemon() -> None:
    """Manage the DeskSearch background daemon.

    The daemon watches your indexed folders for new or changed files
    and re-indexes them automatically in the background.
    """


@daemon.command("start", epilog="""
\b
Examples:
  desksearch daemon start
  desksearch daemon start --no-daemonize
  desksearch daemon start --no-daemonize --tray
""")
@click.option("--no-daemonize", is_flag=True, help="Run in foreground (don't fork)")
@click.option("--tray", is_flag=True, help="Show system tray icon (requires pystray)")
def daemon_start(no_daemonize: bool, tray: bool) -> None:
    """Start the background daemon service."""
    from desksearch.daemon.service import BackgroundService

    config = Config.load()
    service = BackgroundService(config)

    existing = service.read_pid()
    if existing:
        console.print(f"[yellow]Daemon already running (PID {existing})[/yellow]")
        sys.exit(1)

    if no_daemonize:
        console.print("[bold cyan]DeskSearch[/bold cyan] daemon starting in foreground...")
        if tray:
            import threading

            def _run_tray() -> None:
                try:
                    from desksearch.daemon.tray import SystemTray
                    st = SystemTray(service)
                    st.run()
                except Exception as e:
                    console.print(f"[yellow]System tray unavailable: {e}[/yellow]")

            threading.Thread(target=_run_tray, daemon=True, name="tray").start()
        service.start(daemonize=False)
    else:
        console.print("[bold cyan]DeskSearch[/bold cyan] daemon starting...")
        service.start(daemonize=True)


@daemon.command("stop", epilog="""
\b
Examples:
  desksearch daemon stop
""")
def daemon_stop() -> None:
    """Stop the background daemon."""
    from desksearch.daemon.service import BackgroundService

    if BackgroundService.send_stop():
        console.print("[green]✓[/green] Daemon stopped.")
    else:
        console.print("[yellow]No running daemon found.[/yellow]")


@daemon.command("status", epilog="""
\b
Examples:
  desksearch daemon status
  desksearch daemon status --json
""")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON for scripting")
def daemon_status(as_json: bool) -> None:
    """Show daemon status (running, PID, uptime, document counts)."""
    from datetime import datetime, timezone
    from desksearch.daemon.service import BackgroundService

    status_info = BackgroundService.get_status()
    if status_info is None:
        if as_json:
            _print_json({"running": False})
        else:
            console.print("[yellow]Daemon is not running.[/yellow]")
        return

    uptime_str = None
    start_time = status_info.get("start_time")
    if start_time:
        try:
            st = datetime.fromisoformat(start_time)
            uptime = datetime.now(timezone.utc) - st
            h, rem = divmod(int(uptime.total_seconds()), 3600)
            m, s = divmod(rem, 60)
            uptime_str = f"{h}h {m}m {s}s"
        except (ValueError, TypeError):
            pass

    data = {
        "running": True,
        "pid": status_info.get("pid"),
        "uptime": uptime_str,
        "indexing_paused": status_info.get("paused", False),
        "documents": status_info.get("documents"),
        "chunks": status_info.get("chunks"),
        "server": f"http://{status_info.get('host', '127.0.0.1')}:{status_info.get('port', 3777)}",
    }

    if as_json:
        _print_json(data)
        return

    table = Table(title="DeskSearch Daemon", box=box.ROUNDED, show_header=False)
    table.add_column("Metric", style="bold cyan", width=18)
    table.add_column("Value")

    table.add_row("Status", "[bold green]Running[/bold green]")
    table.add_row("PID", str(data["pid"] or "?"))
    if uptime_str:
        table.add_row("Uptime", uptime_str)
    table.add_row("Indexing", "[yellow]Paused[/yellow]" if data["indexing_paused"] else "[green]Active[/green]")
    table.add_row("Documents", str(data["documents"] or "?"))
    table.add_row("Chunks", str(data["chunks"] or "?"))
    table.add_row("Server", data["server"])

    console.print(table)


@daemon.command("install", epilog="""
\b
Examples:
  desksearch daemon install
""")
def daemon_install() -> None:
    """Set up daemon to auto-start on system login."""
    from desksearch.daemon.autostart import install_autostart

    path = install_autostart()
    console.print(f"[green]✓[/green] Autostart installed: {path}")
    console.print("[dim]DeskSearch will start automatically on next login.[/dim]")


@daemon.command("uninstall", epilog="""
\b
Examples:
  desksearch daemon uninstall
""")
def daemon_uninstall() -> None:
    """Remove daemon auto-start from system login."""
    from desksearch.daemon.autostart import uninstall_autostart

    if uninstall_autostart():
        console.print("[green]✓[/green] Autostart removed.")
    else:
        console.print("[yellow]No autostart entry found.[/yellow]")


@daemon.command("logs", epilog="""
\b
Examples:
  desksearch daemon logs
  desksearch daemon logs -n 100
  desksearch daemon logs --follow
""")
@click.option("--lines", "-n", default=50, show_default=True, help="Number of lines to show")
@click.option("--follow", "-f", is_flag=True, help="Follow log output (like tail -f)")
def daemon_logs(lines: int, follow: bool) -> None:
    """Show daemon log output."""
    import subprocess
    from desksearch.daemon.service import LOG_FILE

    if not LOG_FILE.exists():
        console.print("[yellow]No log file found.[/yellow]")
        return

    cmd = ["tail"]
    if follow:
        cmd.append("-f")
    cmd.extend(["-n", str(lines), str(LOG_FILE)])

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli()
