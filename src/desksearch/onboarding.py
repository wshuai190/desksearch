"""First-run onboarding wizard for DeskSearch."""
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Confirm

from desksearch.config import Config, DEFAULT_DATA_DIR

console = Console()

# Folders to always suggest (if they exist)
_ALWAYS_CHECK = ["Documents", "Desktop", "Downloads"]

# Optional folders for developers
_DEV_FOLDERS = ["Projects", "Code", "code", "src", "repos", "dev", "workspace"]

# Optional folders for note-takers
_NOTES_FOLDERS = ["Notes", "Obsidian", "obsidian", "notes", "Notion", "Logseq", "logseq"]


def is_first_run() -> bool:
    """Check if this is the first time DeskSearch is being run."""
    config_path = DEFAULT_DATA_DIR / "config.json"
    return not config_path.exists()


def detect_folders() -> dict[str, list[Path]]:
    """Auto-detect common document folders on the system.

    Returns a dict with categories as keys and lists of existing paths as values.
    """
    home = Path.home()
    result: dict[str, list[Path]] = {
        "documents": [],
        "developer": [],
        "notes": [],
    }

    for name in _ALWAYS_CHECK:
        p = home / name
        if p.is_dir():
            result["documents"].append(p)

    for name in _DEV_FOLDERS:
        p = home / name
        if p.is_dir():
            result["developer"].append(p)

    for name in _NOTES_FOLDERS:
        p = home / name
        if p.is_dir():
            result["notes"].append(p)

    return result


def run_onboarding_wizard() -> Config:
    """Run the interactive CLI onboarding wizard. Returns the saved Config."""
    console.print()
    console.print(
        Panel(
            "[bold cyan]Welcome to DeskSearch![/bold cyan]\n\n"
            "Private semantic search for your local files.\n"
            "Everything runs locally — nothing leaves your machine.",
            border_style="cyan",
        )
    )

    # Detect folders
    detected = detect_folders()
    all_folders: list[Path] = []
    for paths in detected.values():
        all_folders.extend(paths)

    if not all_folders:
        console.print("[yellow]No common folders detected. Using ~/Documents as default.[/yellow]")
        all_folders = [Path.home() / "Documents"]

    # Present detected folders
    console.print("\n[bold]Detected folders to index:[/bold]\n")

    numbered: list[tuple[int, Path, str]] = []
    idx = 1

    if detected["documents"]:
        for p in detected["documents"]:
            console.print(f"  [green]{idx}.[/green] {p}  [dim](documents)[/dim]")
            numbered.append((idx, p, "documents"))
            idx += 1

    if detected["developer"]:
        for p in detected["developer"]:
            console.print(f"  [blue]{idx}.[/blue] {p}  [dim](developer)[/dim]")
            numbered.append((idx, p, "developer"))
            idx += 1

    if detected["notes"]:
        for p in detected["notes"]:
            console.print(f"  [magenta]{idx}.[/magenta] {p}  [dim](notes)[/dim]")
            numbered.append((idx, p, "notes"))
            idx += 1

    console.print()

    # Let user confirm
    if Confirm.ask("[bold]Index all detected folders?[/bold]", default=True):
        selected = [p for _, p, _ in numbered]
    else:
        console.print(
            "\nEnter folder numbers to include (comma-separated), or press Enter for all:"
        )
        raw = console.input("[bold]> [/bold]").strip()
        if not raw:
            selected = [p for _, p, _ in numbered]
        else:
            chosen_nums = set()
            for part in raw.split(","):
                part = part.strip()
                if part.isdigit():
                    chosen_nums.add(int(part))
            selected = [p for n, p, _ in numbered if n in chosen_nums]
            if not selected:
                console.print("[yellow]No valid selections. Using all detected folders.[/yellow]")
                selected = [p for _, p, _ in numbered]

    console.print(f"\n[bold]Selected {len(selected)} folder(s) for indexing.[/bold]")

    # Create config and save
    config = Config(index_paths=selected)
    config.save()
    console.print(f"[green]Config saved to {config.data_dir / 'config.json'}[/green]\n")

    # Start initial indexing
    if Confirm.ask("[bold]Start indexing now?[/bold]", default=True):
        run_initial_index(config)

    # Suggest daemon
    console.print()
    console.print(
        Panel(
            "[bold]Tip:[/bold] Run [cyan]desksearch daemon install[/cyan] to keep your index\n"
            "up-to-date automatically in the background.",
            border_style="dim",
        )
    )

    console.print("[bold green]Setup complete![/bold green] Run [cyan]desksearch[/cyan] to start searching.\n")
    return config


def run_initial_index(config: Config) -> None:
    """Run initial indexing with a nice progress display."""
    import logging
    from desksearch.core.search import HybridSearchEngine
    from desksearch.indexer.pipeline import IndexingPipeline, StatusType

    # Suppress noisy log messages during CLI indexing (parser warnings, etc.)
    logging.getLogger("desksearch").setLevel(logging.WARNING)

    engine = HybridSearchEngine(config)
    pipeline = IndexingPipeline(config, search_engine=engine)

    # Warm up the embedding model so the first file doesn't stall
    console.print("[dim]Loading embedding model...[/dim]")
    pipeline.embedder.warmup()
    console.print("[dim]Model ready.[/dim]\n")

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Indexing files...", total=None)
            total_indexed = 0
            total_errors = 0
            total_skipped = 0
            discovered = 0
            files_parsed = 0

            for path in config.index_paths:
                if not path.is_dir():
                    continue
                progress.update(task, description=f"[cyan]Scanning {path.name}/...")
                gen = pipeline.index_directory(path)

                try:
                    while True:
                        status = next(gen)
                        if status.status == StatusType.DISCOVERY:
                            # Parse discovered count from message if available
                            if status.message and "found" in status.message.lower():
                                try:
                                    parts = status.message.split()
                                    for i, w in enumerate(parts):
                                        if w.lower() == "found":
                                            discovered = int(parts[i + 1])
                                            progress.update(task, total=discovered)
                                            break
                                except (IndexError, ValueError):
                                    pass
                        elif status.status == StatusType.PARSING and status.file:
                            files_parsed += 1
                            progress.update(
                                task,
                                description=f"[cyan]Parsing [bold]{files_parsed}[/bold]/{discovered or '?'} — {Path(status.file).name}",
                            )
                        elif status.status == StatusType.EMBEDDING:
                            progress.update(
                                task,
                                description=f"[cyan]Embedding batch... ({files_parsed} files parsed)",
                            )
                        elif status.status == StatusType.COMPLETE and status.file:
                            total_indexed += 1
                            progress.update(
                                task,
                                advance=1,
                                description=f"[cyan]Indexed [bold]{total_indexed}[/bold] files — {Path(status.file).name}",
                            )
                        elif status.status == StatusType.ERROR:
                            total_errors += 1
                            progress.update(task, advance=1)
                        elif status.status == StatusType.SKIPPED:
                            total_skipped += 1
                            progress.update(task, advance=1)
                except StopIteration:
                    pass

        console.print(
            f"\n[bold green]Indexing complete:[/bold green] "
            f"{total_indexed} files indexed, {total_skipped} skipped, {total_errors} errors"
        )
        console.print(
            f"Total: {pipeline.store.document_count()} documents, "
            f"{pipeline.store.chunk_count()} chunks"
        )
    finally:
        pipeline.close()


def add_folder(folder_path: str) -> None:
    """Add a folder to the index and start indexing it."""
    path = Path(folder_path).expanduser().resolve()
    if not path.is_dir():
        console.print(f"[red]Not a directory:[/red] {path}")
        return

    config = Config.load()

    if path in config.index_paths:
        console.print(f"[yellow]Already indexed:[/yellow] {path}")
        return

    config.index_paths.append(path)
    config.save()
    console.print(f"[green]Added:[/green] {path}")

    # Index the new folder
    run_initial_index(Config.load())


def remove_folder(folder_path: str) -> None:
    """Remove a folder from the watch list."""
    path = Path(folder_path).expanduser().resolve()
    config = Config.load()

    matching = [p for p in config.index_paths if p.resolve() == path]
    if not matching:
        console.print(f"[yellow]Not in index paths:[/yellow] {path}")
        console.print("Current paths:")
        for p in config.index_paths:
            console.print(f"  - {p}")
        return

    for m in matching:
        config.index_paths.remove(m)
    config.save()
    console.print(f"[green]Removed:[/green] {path}")
    console.print("[dim]Note: existing indexed files from this folder remain in the index.[/dim]")
    console.print("[dim]Run 'desksearch index' to rebuild if needed.[/dim]")
