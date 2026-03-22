#!/usr/bin/env python3
"""Comprehensive benchmark suite for DeskSearch.

Measures indexing speed, search latency, memory footprint, index size,
and search quality (precision/recall) across BM25, dense, and hybrid modes.

Usage:
    python benchmarks/benchmark.py [--output benchmarks/results.md]
"""
import argparse
import gc
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import psutil

# Ensure the project is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from desksearch.config import Config
from desksearch.core.search import HybridSearchEngine, SearchResult
from desksearch.indexer.embedder import Embedder
from desksearch.indexer.store import MetadataStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROCESS = psutil.Process(os.getpid())


def mem_mb() -> float:
    """Current RSS in megabytes."""
    return _PROCESS.memory_info().rss / (1024 * 1024)


def fmt_mb(val: float) -> str:
    return f"{val:.1f} MB"


def fmt_ms(val: float) -> str:
    return f"{val:.1f} ms"


def fmt_s(val: float) -> str:
    return f"{val:.2f} s"


def percentile(data: list[float], pct: int) -> float:
    """Return the *pct*-th percentile of *data*."""
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * pct / 100
    f = int(k)
    c = f + 1 if f + 1 < len(s) else f
    return s[f] + (k - f) * (s[c] - s[f])


# ---------------------------------------------------------------------------
# Test queries with known-relevant categories
# ---------------------------------------------------------------------------

# Each entry: (query, set of category substrings expected in top-5 results)
# Categories in corpus: cooking, machine_learning, programming, research,
#                       systems, travel

TEST_QUERIES = [
    # --- Keyword-friendly (BM25 should do well) ---
    ("Maillard reaction amino acids sugars", {"cooking"}),
    ("Rust ownership borrow checker", {"programming"}),
    ("Kafka message queue asynchronous", {"systems"}),
    ("attention mechanism transformer", {"research"}),
    ("gradient descent backpropagation", {"machine_learning"}),
    ("Japan rail system Shinkansen", {"travel"}),
    ("fermentation kimchi sauerkraut", {"cooking"}),
    ("Python garbage collection memory", {"programming"}),
    ("load balancer distributed system", {"systems"}),
    ("convolutional neural network image", {"machine_learning"}),

    # --- Semantic / conceptual (dense should help) ---
    ("how to brown meat properly", {"cooking"}),
    ("preventing memory bugs at compile time", {"programming"}),
    ("sending messages between microservices", {"systems"}),
    ("training models to understand language", {"machine_learning", "research"}),
    ("exploring cities in Asia", {"travel"}),
    ("preserving food with bacteria", {"cooking"}),
    ("finding similar vectors efficiently", {"machine_learning", "research"}),
    ("making code run faster", {"programming", "systems"}),
    ("booking accommodation abroad", {"travel"}),
    ("scientific paper writing methodology", {"research"}),
]


# ---------------------------------------------------------------------------
# Benchmark: Indexing Speed
# ---------------------------------------------------------------------------

def bench_indexing_speed(config: Config, store: MetadataStore) -> dict:
    """Measure indexing throughput for different corpus sizes."""
    from desksearch.indexer.chunker import chunk_text
    from desksearch.indexer.parsers import parse_file

    docs = store.all_documents()
    # Gather files that still exist on disk
    existing = [d for d in docs if Path(d.path).exists()]
    if not existing:
        return {"error": "No indexable files found on disk"}

    results = {}
    embedder = Embedder(config.embedding_model)
    embedder.warmup()

    for target in (100, 500, min(1000, len(existing))):
        subset = existing[:target]
        texts: list[str] = []
        total_chunks = 0

        gc.collect()
        mem_before = mem_mb()
        t0 = time.perf_counter()

        for doc in subset:
            content = parse_file(Path(doc.path))
            if content is None:
                continue
            chunks = chunk_text(
                content,
                source_file=doc.path,
                chunk_size=config.chunk_size,
                chunk_overlap=config.chunk_overlap,
            )
            total_chunks += len(chunks)
            texts.extend(c.text for c in chunks)

        # Embed all at once (like batch pipeline)
        if texts:
            _ = embedder.embed(texts, batch_size=64)

        elapsed = time.perf_counter() - t0
        mem_after = mem_mb()

        results[f"{target}_files"] = {
            "files": len(subset),
            "chunks": total_chunks,
            "time_s": round(elapsed, 2),
            "files_per_sec": round(len(subset) / elapsed, 1),
            "chunks_per_sec": round(total_chunks / elapsed, 1),
            "mem_delta_mb": round(mem_after - mem_before, 1),
            "peak_mem_mb": round(mem_after, 1),
        }

    embedder.cooldown()
    return results


# ---------------------------------------------------------------------------
# Benchmark: Search Speed
# ---------------------------------------------------------------------------

def bench_search_speed(config: Config) -> dict:
    """Measure cold-start, warm search latency, and throughput."""
    embedder = Embedder(config.embedding_model)

    # Make sure model is unloaded for cold-start test
    embedder.cooldown()
    gc.collect()
    time.sleep(0.5)

    engine = HybridSearchEngine(config)

    # --- Cold start (includes model loading) ---
    query = "machine learning neural network"
    t0 = time.perf_counter()
    q_emb = embedder.embed_query(query)
    cold_results = engine.search_sync(query, q_emb, top_k=10)
    cold_ms = (time.perf_counter() - t0) * 1000

    # --- Warm search: 50 queries ---
    queries = [q for q, _ in TEST_QUERIES]
    # Pre-embed all queries (warm model)
    query_embeddings = {q: embedder.embed_query(q) for q in queries}

    latencies: list[float] = []
    num_warm = 50
    for i in range(num_warm):
        q = queries[i % len(queries)]
        qe = query_embeddings[q]
        t0 = time.perf_counter()
        _ = engine.search_sync(q, qe, top_k=10)
        latencies.append((time.perf_counter() - t0) * 1000)

    embedder.cooldown()

    return {
        "cold_start_ms": round(cold_ms, 1),
        "cold_results_count": len(cold_results),
        "warm_queries": num_warm,
        "avg_ms": round(statistics.mean(latencies), 2),
        "median_ms": round(statistics.median(latencies), 2),
        "p50_ms": round(percentile(latencies, 50), 2),
        "p95_ms": round(percentile(latencies, 95), 2),
        "p99_ms": round(percentile(latencies, 99), 2),
        "min_ms": round(min(latencies), 2),
        "max_ms": round(max(latencies), 2),
        "qps": round(1000 / statistics.mean(latencies), 1),
    }


# ---------------------------------------------------------------------------
# Benchmark: Memory Footprint
# ---------------------------------------------------------------------------

def bench_memory(config: Config) -> dict:
    """Measure memory at different lifecycle stages."""
    gc.collect()
    time.sleep(0.3)
    idle_mem = mem_mb()

    # After model load (first search)
    embedder = Embedder(config.embedding_model)
    embedder.warmup()
    model_loaded_mem = mem_mb()

    # During embedding (simulate indexing load)
    dummy_texts = ["benchmark test sentence number " + str(i) for i in range(200)]
    _ = embedder.embed(dummy_texts, batch_size=64)
    during_indexing_mem = mem_mb()

    # After cooldown
    embedder.cooldown()
    gc.collect()
    time.sleep(0.5)
    after_cooldown_mem = mem_mb()

    return {
        "idle_mb": round(idle_mem, 1),
        "model_loaded_mb": round(model_loaded_mem, 1),
        "during_indexing_mb": round(during_indexing_mem, 1),
        "after_cooldown_mb": round(after_cooldown_mem, 1),
        "model_overhead_mb": round(model_loaded_mem - idle_mem, 1),
        "memory_reclaimed_mb": round(during_indexing_mem - after_cooldown_mem, 1),
    }


# ---------------------------------------------------------------------------
# Benchmark: Index Size
# ---------------------------------------------------------------------------

def bench_index_size(config: Config, store: MetadataStore) -> dict:
    """Measure on-disk index sizes and compression ratio."""
    data_dir = config.data_dir

    def dir_size(p: Path) -> int:
        if not p.exists():
            return 0
        if p.is_file():
            return p.stat().st_size
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())

    bm25_bytes = dir_size(data_dir / "bm25")
    dense_bytes = dir_size(data_dir / "dense")
    sqlite_bytes = dir_size(data_dir / "metadata.db")
    # Include WAL/SHM
    for suffix in ("-wal", "-shm"):
        wal = data_dir / f"metadata.db{suffix}"
        if wal.exists():
            sqlite_bytes += wal.stat().st_size
    embeddings_bytes = dir_size(data_dir / "embeddings")
    total_bytes = bm25_bytes + dense_bytes + sqlite_bytes + embeddings_bytes

    # Estimate original corpus size
    docs = store.all_documents()
    corpus_bytes = sum(d.size for d in docs)

    def to_mb(b: int) -> float:
        return round(b / (1024 * 1024), 2)

    ratio = round(total_bytes / corpus_bytes, 2) if corpus_bytes > 0 else 0

    return {
        "bm25_mb": to_mb(bm25_bytes),
        "dense_mb": to_mb(dense_bytes),
        "sqlite_mb": to_mb(sqlite_bytes),
        "embeddings_mb": to_mb(embeddings_bytes),
        "total_index_mb": to_mb(total_bytes),
        "corpus_mb": to_mb(corpus_bytes),
        "index_to_corpus_ratio": ratio,
        "doc_count": store.document_count(),
        "chunk_count": store.chunk_count(),
    }


# ---------------------------------------------------------------------------
# Benchmark: Search Quality
# ---------------------------------------------------------------------------

def bench_search_quality(config: Config, store: MetadataStore) -> dict:
    """Measure precision@5, recall@5 for BM25, dense, and hybrid search."""
    embedder = Embedder(config.embedding_model)
    embedder.warmup()

    engine = HybridSearchEngine(config)

    # Build relevance map: chunk_id -> category (directory name)
    docs = store.all_documents()
    chunk_to_category: dict[str, str] = {}
    for doc in docs:
        category = Path(doc.path).parent.name
        chunks = store.get_chunks(doc.id)
        for chunk in chunks:
            chunk_to_category[str(chunk.id)] = category

    # Populate engine with existing data
    # The engine loads from disk (bm25/dense dirs), so doc_texts need populating
    for doc in docs:
        chunks = store.get_chunks(doc.id)
        for chunk in chunks:
            engine.set_doc_text(str(chunk.id), chunk.text)

    modes = {
        "bm25_only": 0.0,    # alpha=0 -> BM25 only
        "dense_only": 1.0,   # alpha=1 -> dense only
        "hybrid": 0.5,       # alpha=0.5 -> balanced
    }

    quality: dict[str, dict] = {}

    for mode_name, alpha in modes.items():
        precisions: list[float] = []
        recalls: list[float] = []

        for query, expected_categories in TEST_QUERIES:
            q_emb = embedder.embed_query(query)
            results = engine.search_sync(query, q_emb, top_k=5, alpha=alpha)

            # Check how many of top-5 results are from expected categories
            relevant_count = 0
            for r in results:
                cat = chunk_to_category.get(r.doc_id, "")
                if cat in expected_categories:
                    relevant_count += 1

            k = min(5, len(results))
            precision = relevant_count / k if k > 0 else 0.0
            # Recall: fraction of expected categories represented
            found_cats = {
                chunk_to_category.get(r.doc_id, "")
                for r in results
            } & expected_categories
            recall = len(found_cats) / len(expected_categories) if expected_categories else 0.0

            precisions.append(precision)
            recalls.append(recall)

        quality[mode_name] = {
            "alpha": alpha,
            "mean_precision_at_5": round(statistics.mean(precisions), 3),
            "mean_recall_at_5": round(statistics.mean(recalls), 3),
            "min_precision": round(min(precisions), 3),
            "max_precision": round(max(precisions), 3),
        }

    embedder.cooldown()

    # Determine winner
    hybrid_p = quality["hybrid"]["mean_precision_at_5"]
    hybrid_r = quality["hybrid"]["mean_recall_at_5"]
    bm25_p = quality["bm25_only"]["mean_precision_at_5"]
    bm25_r = quality["bm25_only"]["mean_recall_at_5"]
    dense_p = quality["dense_only"]["mean_precision_at_5"]
    dense_r = quality["dense_only"]["mean_recall_at_5"]
    quality["summary"] = {
        "hybrid_beats_bm25_precision": hybrid_p >= bm25_p,
        "hybrid_beats_dense_precision": hybrid_p >= dense_p,
        "hybrid_best_recall": hybrid_r >= bm25_r and hybrid_r >= dense_r,
        "hybrid_precision": hybrid_p,
        "hybrid_recall": hybrid_r,
        "bm25_precision": bm25_p,
        "bm25_recall": bm25_r,
        "dense_precision": dense_p,
        "dense_recall": dense_r,
    }

    return quality


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(results: dict) -> str:
    """Generate a Markdown report from benchmark results."""
    lines = [
        "# DeskSearch Benchmark Results",
        "",
        f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Platform:** {sys.platform} / Python {sys.version.split()[0]}",
        f"**CPU:** {psutil.cpu_count(logical=False)} cores ({psutil.cpu_count()} logical)",
        f"**RAM:** {psutil.virtual_memory().total / (1024**3):.0f} GB",
        "",
    ]

    # --- Indexing Speed ---
    lines.append("## 1. Indexing Speed")
    lines.append("")
    idx = results.get("indexing", {})
    if "error" in idx:
        lines.append(f"*{idx['error']}*")
    else:
        lines.append("| Corpus Size | Time | Files/sec | Chunks/sec | Peak Memory |")
        lines.append("|---|---|---|---|---|")
        for key in sorted(idx.keys()):
            d = idx[key]
            lines.append(
                f"| {d['files']} files ({d['chunks']} chunks) "
                f"| {fmt_s(d['time_s'])} "
                f"| {d['files_per_sec']} "
                f"| {d['chunks_per_sec']} "
                f"| {fmt_mb(d['peak_mem_mb'])} |"
            )
    lines.append("")

    # --- Search Speed ---
    lines.append("## 2. Search Latency")
    lines.append("")
    ss = results.get("search_speed", {})
    lines.append(f"- **Cold start** (model load + first query): **{fmt_ms(ss.get('cold_start_ms', 0))}**")
    lines.append(f"- **Warm search** ({ss.get('warm_queries', 0)} queries):")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    for k in ("avg_ms", "p50_ms", "p95_ms", "p99_ms", "min_ms", "max_ms", "qps"):
        label = k.replace("_", " ").upper()
        val = ss.get(k, 0)
        if k == "qps":
            lines.append(f"| {label} | **{val} queries/sec** |")
        else:
            lines.append(f"| {label} | {val} ms |")
    lines.append("")

    # --- Memory ---
    lines.append("## 3. Memory Footprint")
    lines.append("")
    mem = results.get("memory", {})
    lines.append("| State | RSS |")
    lines.append("|---|---|")
    lines.append(f"| Idle (no model) | {fmt_mb(mem.get('idle_mb', 0))} |")
    lines.append(f"| Model loaded | {fmt_mb(mem.get('model_loaded_mb', 0))} |")
    lines.append(f"| During indexing | {fmt_mb(mem.get('during_indexing_mb', 0))} |")
    lines.append(f"| After cooldown | {fmt_mb(mem.get('after_cooldown_mb', 0))} |")
    lines.append("")
    lines.append(f"- Model overhead: **{fmt_mb(mem.get('model_overhead_mb', 0))}**")
    lines.append(f"- Memory reclaimed after cooldown: **{fmt_mb(mem.get('memory_reclaimed_mb', 0))}**")
    lines.append("")

    # --- Index Size ---
    lines.append("## 4. Index Size")
    lines.append("")
    isz = results.get("index_size", {})
    lines.append(f"**Corpus:** {isz.get('doc_count', 0)} documents, {isz.get('chunk_count', 0)} chunks, {isz.get('corpus_mb', 0)} MB on disk")
    lines.append("")
    lines.append("| Component | Size |")
    lines.append("|---|---|")
    lines.append(f"| BM25 (tantivy) | {isz.get('bm25_mb', 0)} MB |")
    lines.append(f"| Dense (FAISS) | {isz.get('dense_mb', 0)} MB |")
    lines.append(f"| SQLite metadata | {isz.get('sqlite_mb', 0)} MB |")
    lines.append(f"| Embeddings (.npy) | {isz.get('embeddings_mb', 0)} MB |")
    lines.append(f"| **Total index** | **{isz.get('total_index_mb', 0)} MB** |")
    lines.append("")
    lines.append(f"**Index-to-corpus ratio:** {isz.get('index_to_corpus_ratio', 0)}x")
    lines.append("")

    # --- Search Quality ---
    lines.append("## 5. Search Quality (Precision@5 / Recall@5)")
    lines.append("")
    sq = results.get("search_quality", {})
    lines.append("| Mode | Alpha | Precision@5 | Recall@5 |")
    lines.append("|---|---|---|---|")
    for mode in ("bm25_only", "dense_only", "hybrid"):
        d = sq.get(mode, {})
        lines.append(
            f"| {mode.replace('_', ' ').title()} "
            f"| {d.get('alpha', '')} "
            f"| **{d.get('mean_precision_at_5', 0):.3f}** "
            f"| {d.get('mean_recall_at_5', 0):.3f} |"
        )
    lines.append("")
    summary = sq.get("summary", {})
    notes = []
    if summary.get("hybrid_best_recall"):
        notes.append(
            f"**Hybrid achieves the best recall** ({summary.get('hybrid_recall', 0):.3f}) "
            f"vs BM25 ({summary.get('bm25_recall', 0):.3f}) and "
            f"dense ({summary.get('dense_recall', 0):.3f}) — it finds relevant "
            f"categories more consistently by combining both signals."
        )
    notes.append(
        f"Precision: hybrid {summary.get('hybrid_precision', 0):.3f}, "
        f"BM25 {summary.get('bm25_precision', 0):.3f}, "
        f"dense {summary.get('dense_precision', 0):.3f}."
    )
    lines.append("> " + " ".join(notes))
    lines.append("")

    # --- 20 test queries ---
    lines.append("### Test Queries")
    lines.append("")
    lines.append("| # | Query | Expected Category |")
    lines.append("|---|---|---|")
    for i, (q, cats) in enumerate(TEST_QUERIES, 1):
        lines.append(f"| {i} | {q} | {', '.join(cats)} |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="DeskSearch benchmarks")
    parser.add_argument(
        "--output", "-o",
        default="benchmarks/results.md",
        help="Output path for Markdown results",
    )
    parser.add_argument(
        "--skip-indexing",
        action="store_true",
        help="Skip the slow indexing benchmark",
    )
    args = parser.parse_args()

    config = Config.load()
    store = MetadataStore(config.data_dir / "metadata.db")

    print(f"DeskSearch Benchmark Suite")
    print(f"  Data dir:   {config.data_dir}")
    print(f"  Documents:  {store.document_count()}")
    print(f"  Chunks:     {store.chunk_count()}")
    print()

    results = {}

    # 1. Index size (fast, run first)
    print("[1/5] Measuring index size...")
    results["index_size"] = bench_index_size(config, store)
    print(f"  Total: {results['index_size']['total_index_mb']} MB "
          f"(ratio: {results['index_size']['index_to_corpus_ratio']}x)")

    # 2. Memory footprint
    print("[2/5] Measuring memory footprint...")
    results["memory"] = bench_memory(config)
    print(f"  Idle: {fmt_mb(results['memory']['idle_mb'])}, "
          f"Model: {fmt_mb(results['memory']['model_loaded_mb'])}")

    # 3. Search speed
    print("[3/5] Measuring search speed (cold + 50 warm queries)...")
    results["search_speed"] = bench_search_speed(config)
    print(f"  Cold: {fmt_ms(results['search_speed']['cold_start_ms'])}, "
          f"Warm avg: {fmt_ms(results['search_speed']['avg_ms'])}, "
          f"QPS: {results['search_speed']['qps']}")

    # 4. Search quality
    print("[4/5] Measuring search quality (20 queries x 3 modes)...")
    results["search_quality"] = bench_search_quality(config, store)
    sq = results["search_quality"]
    print(f"  Hybrid P@5: {sq['hybrid']['mean_precision_at_5']:.3f}, "
          f"BM25: {sq['bm25_only']['mean_precision_at_5']:.3f}, "
          f"Dense: {sq['dense_only']['mean_precision_at_5']:.3f}")

    # 5. Indexing speed
    if args.skip_indexing:
        print("[5/5] Skipping indexing benchmark (--skip-indexing)")
        results["indexing"] = {"skipped": True}
    else:
        print("[5/5] Measuring indexing speed (100/500/1000 files)...")
        results["indexing"] = bench_indexing_speed(config, store)
        for key in sorted(results["indexing"].keys()):
            d = results["indexing"][key]
            print(f"  {d['files']} files: {fmt_s(d['time_s'])} "
                  f"({d['files_per_sec']} files/s, {d['chunks_per_sec']} chunks/s)")

    # Generate report
    report = generate_report(results)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)
    print(f"\nResults written to {output_path}")

    # Also save raw JSON
    json_path = output_path.with_suffix(".json")
    json_path.write_text(json.dumps(results, indent=2))
    print(f"Raw data written to {json_path}")

    store.close()


if __name__ == "__main__":
    main()
