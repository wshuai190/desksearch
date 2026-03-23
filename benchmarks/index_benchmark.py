#!/usr/bin/env python3
"""Indexing pipeline benchmark.

Creates 500 test files (mix of .txt, .md, .py) in a temp dir, runs the
indexing pipeline, and reports throughput and per-stage timing.

Usage:
    python benchmarks/index_benchmark.py
"""
import gc
import os
import resource
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from desksearch.config import Config
from desksearch.indexer.pipeline import IndexingPipeline, StatusType


def create_test_files(directory: Path, count: int = 500) -> list[Path]:
    """Create a mix of test files for benchmarking."""
    files = []
    templates = {
        ".txt": "This is a test document number {i}.\n\n"
                "It contains multiple paragraphs of text to simulate real content.\n"
                "The quick brown fox jumps over the lazy dog. " * 10 + "\n\n"
                "Section {i}.1: Introduction\n"
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 5 + "\n\n"
                "Section {i}.2: Details\n"
                "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. " * 5 + "\n\n"
                "Section {i}.3: Conclusion\n"
                "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris. " * 5,

        ".md": "# Document {i}\n\n"
               "## Overview\n\n"
               "This markdown document covers topic {i} in detail.\n\n"
               "## Key Points\n\n"
               "- Point one about document {i}\n"
               "- Point two with more details\n"
               "- Point three explaining concepts\n\n"
               "## Technical Details\n\n"
               "```python\ndef example_{i}():\n    return 'result'\n```\n\n"
               "The implementation above demonstrates the core concept.\n"
               "Additional context and explanation follows here. " * 10 + "\n\n"
               "## References\n\n"
               "1. Reference one for document {i}\n"
               "2. Reference two with supporting material\n",

        ".py": '"""Module {i}: Example Python file for benchmarking."""\n\n'
               "import os\nimport sys\nfrom pathlib import Path\n\n\n"
               "# Constants\nMAX_ITEMS = {i}\nDEFAULT_NAME = 'benchmark_{i}'\n\n\n"
               "class Handler{i}:\n"
               '    """Handler for processing item {i}."""\n\n'
               "    def __init__(self, name: str = DEFAULT_NAME):\n"
               "        self.name = name\n"
               "        self.items = []\n\n"
               "    def process(self, data: dict) -> dict:\n"
               '        """Process a single data item."""\n'
               "        result = {{}}\n"
               "        for key, value in data.items():\n"
               "            result[key] = str(value).upper()\n"
               "        self.items.append(result)\n"
               "        return result\n\n"
               "    def summary(self) -> str:\n"
               '        """Return a summary of processed items."""\n'
               "        return f'Processed {{len(self.items)}} items'\n\n\n"
               "def main():\n"
               "    handler = Handler{i}()\n"
               "    for j in range({i}):\n"
               "        handler.process({{'id': j, 'value': f'item_{{j}}'}})\n"
               "    print(handler.summary())\n\n\n"
               "if __name__ == '__main__':\n"
               "    main()\n",
    }

    extensions = list(templates.keys())
    for i in range(count):
        ext = extensions[i % len(extensions)]
        fname = f"test_{i:04d}{ext}"
        fpath = directory / fname
        fpath.write_text(templates[ext].format(i=i))
        files.append(fpath)

    return files


def get_peak_memory_mb() -> float:
    """Get peak RSS in MB (macOS/Linux)."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # macOS reports in bytes, Linux in KB
    if sys.platform == "darwin":
        return usage.ru_maxrss / (1024 * 1024)
    return usage.ru_maxrss / 1024


def run_benchmark(n_files: int = 500) -> dict:
    """Run the indexing benchmark and return results."""
    tmpdir = tempfile.mkdtemp(prefix="desksearch_bench_")
    data_dir = Path(tmpdir) / "data"
    files_dir = Path(tmpdir) / "files"
    files_dir.mkdir()
    data_dir.mkdir()

    print(f"📁 Creating {n_files} test files...")
    t0 = time.perf_counter()
    files = create_test_files(files_dir, count=n_files)
    create_time = time.perf_counter() - t0
    print(f"   Created {len(files)} files in {create_time:.2f}s")

    # Configure pipeline (no search engine — pure pipeline benchmark)
    config = Config(
        data_dir=data_dir,
        index_paths=[files_dir],
        file_extensions=[".txt", ".md", ".py"],
    )

    mem_before = get_peak_memory_mb()
    gc.collect()

    print(f"\n🚀 Running indexing pipeline...")
    pipeline = IndexingPipeline(config=config)
    summary = None

    t_start = time.perf_counter()
    gen = pipeline.index_directory(files_dir)
    try:
        while True:
            status = next(gen)
            if status.status == StatusType.COMPLETE and status.current and status.total:
                if status.current % 100 == 0 or status.current == status.total:
                    elapsed = time.perf_counter() - t_start
                    print(f"   Progress: {status.current}/{status.total} "
                          f"({elapsed:.1f}s, {status.current/elapsed:.0f} files/sec)")
    except StopIteration as e:
        summary = e.value

    elapsed = time.perf_counter() - t_start
    mem_after = get_peak_memory_mb()

    pipeline.close()

    # Results
    results = {
        "n_files": n_files,
        "elapsed_sec": elapsed,
        "files_per_sec": n_files / elapsed if elapsed > 0 else 0,
        "peak_memory_mb": mem_after,
        "memory_delta_mb": mem_after - mem_before,
    }

    if summary:
        results.update(summary)

    print(f"\n{'='*60}")
    print(f"📊 BENCHMARK RESULTS")
    print(f"{'='*60}")
    print(f"  Files indexed:    {results.get('indexed', n_files)}")
    print(f"  Total chunks:     {results.get('total_chunks', 'N/A')}")
    print(f"  Total time:       {elapsed:.2f}s")
    print(f"  Files/sec:        {results.get('files_per_sec', 0):.1f}")
    print(f"  Chunks/sec:       {results.get('chunks_per_sec', 0):.0f}")
    print(f"  Peak memory:      {mem_after:.0f} MB")
    print(f"  Memory delta:     {mem_after - mem_before:.0f} MB")

    stage_times = results.get("stage_times", {})
    if stage_times:
        print(f"\n  Per-stage timing:")
        for stage, secs in stage_times.items():
            pct = (secs / elapsed * 100) if elapsed > 0 else 0
            print(f"    {stage:12s}: {secs:6.2f}s ({pct:5.1f}%)")

    print(f"{'='*60}")

    # Re-index benchmark (should be near-instant with content hash)
    print(f"\n🔄 Re-indexing (unchanged files — should be near-instant)...")
    pipeline2 = IndexingPipeline(config=config)
    t_reindex = time.perf_counter()
    gen2 = pipeline2.index_directory(files_dir)
    reindex_summary = None
    try:
        while True:
            next(gen2)
    except StopIteration as e:
        reindex_summary = e.value
    reindex_elapsed = time.perf_counter() - t_reindex
    pipeline2.close()

    print(f"  Re-index time:    {reindex_elapsed:.3f}s")
    if reindex_summary:
        print(f"  Skipped:          {reindex_summary.get('skipped', 0)}")
        print(f"  Re-indexed:       {reindex_summary.get('indexed', 0)}")
    results["reindex_sec"] = reindex_elapsed

    # Cleanup
    shutil.rmtree(tmpdir, ignore_errors=True)
    return results


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    run_benchmark(n)
