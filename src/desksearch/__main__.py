"""CLI entry point for DeskSearch.

Usage:
    desksearch                         # First run → onboarding; otherwise → serve
    desksearch setup                   # Re-run the onboarding wizard

import os as _os
_os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    desksearch add ~/my-folder         # Add a folder to watch + index it
    desksearch remove ~/old-folder     # Stop watching a folder
    desksearch serve [--host HOST] [--port PORT]
    desksearch index PATH [PATH ...]
    desksearch search QUERY
    desksearch status
    desksearch config [--set KEY=VALUE]
    desksearch daemon start|stop|status|install|uninstall|logs
"""
import sys
import webbrowser
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from desksearch.config import Config

console = Console()


class _DefaultGroup(click.Group):
    """Click group that runs onboarding or serve when invoked with no subcommand."""

    def invoke(self, ctx: click.Context) -> None:
        if ctx.invoked_subcommand is None:
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
    """DeskSearch — private semantic search for your local files."""


# ---------------------------------------------------------------------------
# setup (onboarding)
# ---------------------------------------------------------------------------


@cli.command()
def setup() -> None:
    """Run (or re-run) the first-time setup wizard."""
    from desksearch.onboarding import run_onboarding_wizard

    run_onboarding_wizard()


# ---------------------------------------------------------------------------
# add / remove folders
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("folder", type=click.Path())
def add(folder: str) -> None:
    """Add a folder to the watch list and index it."""
    from desksearch.onboarding import add_folder

    add_folder(folder)


@cli.command()
@click.argument("folder", type=click.Path())
def remove(folder: str) -> None:
    """Remove a folder from the watch list."""
    from desksearch.onboarding import remove_folder

    remove_folder(folder)


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--host", default=None, help="Bind host (default: from config)")
@click.option("--port", default=None, type=int, help="Bind port (default: from config)")
@click.option("--no-browser", is_flag=True, help="Don't auto-open the browser")
def serve(host: str | None, port: int | None, no_browser: bool) -> None:
    """Start the DeskSearch web server."""
    import uvicorn

    from desksearch.api.server import create_app
    from desksearch.indexer.store import MetadataStore

    config = Config.load()
    host = host or config.host
    port = port or config.port

    app = create_app(config)

    # Startup banner with indexed file count
    store = MetadataStore(config.data_dir / "metadata.db")
    doc_count = store.document_count()
    chunk_count = store.chunk_count()
    store.close()

    url = f"http://{host}:{port}"
    banner = (
        f"[bold cyan]DeskSearch[/bold cyan] v0.1.0\n\n"
        f"  Search URL:  [link]{url}[/link]\n"
        f"  Documents:   [bold]{doc_count}[/bold] files indexed\n"
        f"  Chunks:      [bold]{chunk_count}[/bold] searchable chunks\n"
        f"  Data dir:    {config.data_dir}"
    )
    console.print(Panel(banner, title="[bold green]Ready[/bold green]", border_style="green"))

    if not no_browser:
        import threading

        def _open_browser() -> None:
            import time

            time.sleep(1.0)
            webbrowser.open(url)

        threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="info")


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
def index(paths: tuple[str, ...]) -> None:
    """Index the specified files or directories."""
    from desksearch.core.search import HybridSearchEngine
    from desksearch.indexer.pipeline import IndexingPipeline, StatusType

    config = Config.load()
    resolved = [Path(p).resolve() for p in paths]

    console.print(f"[bold]Indexing {len(resolved)} path(s)...[/]")
    for p in resolved:
        console.print(f"  * {p}")

    engine = HybridSearchEngine(config)
    pipeline = IndexingPipeline(config, search_engine=engine)

    try:
        total_indexed = 0
        total_errors = 0

        for path in resolved:
            if path.is_dir():
                gen = pipeline.index_directory(path)
            else:
                gen = pipeline.index_file(path)

            try:
                while True:
                    status = next(gen)
                    if status.status == StatusType.COMPLETE and status.file:
                        console.print(f"  [green]OK[/green] {Path(status.file).name} ({status.message})")
                        total_indexed += 1
                    elif status.status == StatusType.ERROR:
                        console.print(f"  [red]ERR[/red] {status.file}: {status.message}")
                        total_errors += 1
                    elif status.status == StatusType.SKIPPED:
                        console.print(f"  [dim]SKIP[/dim] {Path(status.file).name}")
                    elif status.status == StatusType.DISCOVERY:
                        console.print(f"  [blue]{status.message}[/blue]")
            except StopIteration:
                pass

        console.print(
            f"\n[bold green]Done:[/bold green] {total_indexed} files indexed, "
            f"{total_errors} errors"
        )
        console.print(
            f"Total: {pipeline.store.document_count()} documents, "
            f"{pipeline.store.chunk_count()} chunks"
        )
    finally:
        pipeline.close()


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=10, help="Max results to show")
@click.option("--type", "file_type", default=None, help="Filter by file type")
def search(query: str, limit: int, file_type: str | None) -> None:
    """Search your indexed files from the command line."""
    from desksearch.core.search import HybridSearchEngine
    from desksearch.indexer.embedder import Embedder
    from desksearch.indexer.store import MetadataStore

    config = Config.load()
    store = MetadataStore(config.data_dir / "metadata.db")

    if store.document_count() == 0:
        console.print("[yellow]No files indexed yet. Run 'desksearch index <path>' first.[/yellow]")
        store.close()
        return

    embedder = Embedder(config.embedding_model)
    engine = HybridSearchEngine(config)

    # Warm engine from saved data
    from desksearch.api.server import _warm_search_engine
    _warm_search_engine(engine, store, embedder, config)

    console.print(f'[bold]Searching for:[/] "{query}"\n')

    query_embedding = embedder.embed_query(query)
    results = engine.search_sync(query, query_embedding, top_k=limit * 2)

    shown = 0
    for r in results:
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

        shown += 1
        snippet = r.snippets[0].text if r.snippets else chunk.text[:150]
        console.print(f"[bold cyan]{shown}.[/bold cyan] {doc.filename} [dim]({ext})[/dim]  score={r.score:.4f}")
        console.print(f"   [dim]{doc.path}[/dim]")
        console.print(f"   {snippet}\n")

        if shown >= limit:
            break

    if shown == 0:
        console.print("[yellow]No results found.[/yellow]")
    else:
        console.print(f"[dim]Showing {shown} result(s)[/dim]")

    store.close()


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@cli.command()
def status() -> None:
    """Show index statistics."""
    from desksearch.indexer.store import MetadataStore

    config = Config.load()
    store = MetadataStore(config.data_dir / "metadata.db")

    doc_count = store.document_count()
    chunk_count = store.chunk_count()

    # Compute index size
    index_size_mb = 0.0
    try:
        if config.data_dir.exists():
            total_bytes = sum(
                f.stat().st_size for f in config.data_dir.rglob("*") if f.is_file()
            )
            index_size_mb = total_bytes / (1024 * 1024)
    except OSError:
        pass

    table = Table(title="DeskSearch Status")
    table.add_column("Metric", style="bold")
    table.add_column("Value")

    table.add_row("Data directory", str(config.data_dir))
    table.add_row("Indexed paths", ", ".join(str(p) for p in config.index_paths))
    table.add_row("Embedding model", config.embedding_model)
    table.add_row("Chunk size", str(config.chunk_size))
    table.add_row("Total documents", str(doc_count))
    table.add_row("Total chunks", str(chunk_count))
    table.add_row("Index size", f"{index_size_mb:.1f} MB")

    console.print(table)
    store.close()


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--set", "updates", multiple=True, help="Set KEY=VALUE (repeatable)")
def config(updates: tuple[str, ...]) -> None:
    """Show or update configuration."""
    cfg = Config.load()

    if not updates:
        table = Table(title="DeskSearch Configuration")
        table.add_column("Key", style="bold")
        table.add_column("Value")
        for key, value in cfg.model_dump(mode="json").items():
            table.add_row(key, str(value))
        console.print(table)
        return

    data = cfg.model_dump()
    for item in updates:
        if "=" not in item:
            console.print(f"[red]Invalid format:[/] {item}  (expected KEY=VALUE)")
            sys.exit(1)
        key, value = item.split("=", 1)
        if key not in data:
            console.print(f"[red]Unknown config key:[/] {key}")
            sys.exit(1)
        current = data[key]
        if isinstance(current, bool):
            data[key] = value.lower() in ("true", "1", "yes")
        elif isinstance(current, int):
            data[key] = int(value)
        elif isinstance(current, list):
            data[key] = [v.strip() for v in value.split(",")]
        else:
            data[key] = value

    cfg = Config(**data)
    cfg.save()
    console.print("[green]Configuration saved.[/]")


# ---------------------------------------------------------------------------
# daemon
# ---------------------------------------------------------------------------


@cli.group()
def daemon() -> None:
    """Manage the DeskSearch background daemon."""


@daemon.command("start")
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

            def _run_tray():
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
        # If we get here, we're in the child process (parent already exited)


@daemon.command("stop")
def daemon_stop() -> None:
    """Stop the background daemon."""
    from desksearch.daemon.service import BackgroundService

    if BackgroundService.send_stop():
        console.print("[green]Daemon stopped.[/green]")
    else:
        console.print("[yellow]No running daemon found.[/yellow]")


@daemon.command("status")
def daemon_status() -> None:
    """Show daemon status."""
    from datetime import datetime, timezone

    from desksearch.daemon.service import BackgroundService

    status_info = BackgroundService.get_status()
    if status_info is None:
        console.print("[yellow]Daemon is not running.[/yellow]")
        return

    table = Table(title="DeskSearch Daemon")
    table.add_column("Metric", style="bold")
    table.add_column("Value")

    table.add_row("Status", "[green]Running[/green]")
    table.add_row("PID", str(status_info.get("pid", "?")))

    start_time = status_info.get("start_time")
    if start_time:
        try:
            st = datetime.fromisoformat(start_time)
            uptime = datetime.now(timezone.utc) - st
            hours, remainder = divmod(int(uptime.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            table.add_row("Uptime", f"{hours}h {minutes}m {seconds}s")
        except (ValueError, TypeError):
            pass

    paused = status_info.get("paused", False)
    table.add_row("Indexing", "[yellow]Paused[/yellow]" if paused else "[green]Active[/green]")
    table.add_row("Documents", str(status_info.get("documents", "?")))
    table.add_row("Chunks", str(status_info.get("chunks", "?")))
    table.add_row(
        "Server",
        f"http://{status_info.get('host', '127.0.0.1')}:{status_info.get('port', 3777)}",
    )

    console.print(table)


@daemon.command("install")
def daemon_install() -> None:
    """Set up daemon to auto-start on system login."""
    from desksearch.daemon.autostart import install_autostart

    path = install_autostart()
    console.print(f"[green]Autostart installed:[/green] {path}")
    console.print("DeskSearch will start automatically on next login.")


@daemon.command("uninstall")
def daemon_uninstall() -> None:
    """Remove daemon auto-start from system login."""
    from desksearch.daemon.autostart import uninstall_autostart

    if uninstall_autostart():
        console.print("[green]Autostart removed.[/green]")
    else:
        console.print("[yellow]No autostart entry found.[/yellow]")


@daemon.command("logs")
@click.option("--lines", "-n", default=50, help="Number of lines to show")
@click.option("--follow", "-f", is_flag=True, help="Follow log output")
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
