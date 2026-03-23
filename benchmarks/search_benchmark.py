#!/usr/bin/env python3
"""Search speed benchmark for DeskSearch.

Creates a synthetic index with 50k chunks (64-dimensional random embeddings),
runs 1000 searches, and reports latency percentiles and throughput.

Usage:
    cd /Users/dylanwang/Projects/localsearch
    source .venv/bin/activate
    python benchmarks/search_benchmark.py
"""
from __future__ import annotations

import gc
import statistics
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

# Ensure the project source is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from desksearch.config import Config
from desksearch.core.fusion import weighted_rrf

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
NUM_CHUNKS = 50_000
NUM_QUERIES = 1_000
DIMENSION = 64
TOP_K = 10
RRF_K = 60
ALPHA = 0.4
WARMUP_QUERIES = 50


def _generate_random_embeddings(n: int, dim: int) -> np.ndarray:
    """Generate L2-normalised random float32 embeddings."""
    vecs = np.random.randn(n, dim).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-10)
    return vecs / norms


def benchmark_faiss_search(index, query_embeddings: np.ndarray) -> list[float]:
    """Benchmark raw FAISS search (no fusion, no snippets)."""
    latencies: list[float] = []
    for i in range(len(query_embeddings)):
        q = query_embeddings[i : i + 1]
        t0 = time.perf_counter()
        index.search(q, TOP_K)
        latencies.append((time.perf_counter() - t0) * 1000)
    return latencies


def benchmark_rrf_fusion(
    bm25_results_list: list[list[tuple[str, float]]],
    dense_results_list: list[list[tuple[str, float]]],
) -> list[float]:
    """Benchmark RRF fusion only."""
    latencies: list[float] = []
    for bm25_r, dense_r in zip(bm25_results_list, dense_results_list):
        t0 = time.perf_counter()
        weighted_rrf(bm25_r, dense_r, alpha=ALPHA, k=RRF_K)
        latencies.append((time.perf_counter() - t0) * 1000)
    return latencies


def benchmark_hybrid_search(engine, query_embeddings: np.ndarray, queries: list[str]) -> list[float]:
    """Benchmark the full hybrid search pipeline (sync path, no caching)."""
    latencies: list[float] = []
    for i in range(len(queries)):
        # Clear cache to measure real search cost every time.
        if engine._cache:
            engine._cache.clear()
        t0 = time.perf_counter()
        engine.search_sync(
            queries[i], query_embeddings[i], top_k=TOP_K, max_snippets=0
        )
        latencies.append((time.perf_counter() - t0) * 1000)
    return latencies


def _percentile(data: list[float], p: float) -> float:
    """Return the p-th percentile of sorted data."""
    data_sorted = sorted(data)
    idx = int(len(data_sorted) * p / 100)
    idx = min(idx, len(data_sorted) - 1)
    return data_sorted[idx]


def _report(label: str, latencies: list[float]) -> None:
    """Print latency stats for a benchmark run."""
    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)
    p99 = _percentile(latencies, 99)
    mean = statistics.mean(latencies)
    qps = 1000.0 / mean if mean > 0 else float("inf")
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    print(f"  Queries:   {len(latencies)}")
    print(f"  Mean:      {mean:.2f} ms")
    print(f"  p50:       {p50:.2f} ms")
    print(f"  p95:       {p95:.2f} ms")
    print(f"  p99:       {p99:.2f} ms")
    print(f"  Min:       {min(latencies):.2f} ms")
    print(f"  Max:       {max(latencies):.2f} ms")
    print(f"  QPS:       {qps:.0f} searches/sec")


def main() -> None:
    print(f"DeskSearch Search Speed Benchmark")
    print(f"  Chunks: {NUM_CHUNKS:,}  |  Queries: {NUM_QUERIES:,}  |  Dim: {DIMENSION}  |  top_k: {TOP_K}")

    np.random.seed(42)

    # ------------------------------------------------------------------
    # 1. Build FAISS index
    # ------------------------------------------------------------------
    print("\n[1/5] Building FAISS index with {0:,} vectors...".format(NUM_CHUNKS))
    import faiss

    embeddings = _generate_random_embeddings(NUM_CHUNKS, DIMENSION)
    doc_ids = [f"doc_{i}" for i in range(NUM_CHUNKS)]

    t0 = time.perf_counter()
    # Use HNSW like the real engine does at this scale
    hnsw = faiss.IndexHNSWFlat(DIMENSION, 32)
    hnsw.hnsw.efConstruction = 200
    hnsw.hnsw.efSearch = 32  # tuned for speed
    index = faiss.IndexIDMap(hnsw)
    int_ids = np.arange(NUM_CHUNKS, dtype=np.int64)
    index.add_with_ids(embeddings, int_ids)
    build_time = time.perf_counter() - t0
    print(f"  Index built in {build_time:.1f}s ({index.ntotal:,} vectors)")

    # ------------------------------------------------------------------
    # 2. Generate query embeddings
    # ------------------------------------------------------------------
    print(f"\n[2/5] Generating {NUM_QUERIES + WARMUP_QUERIES} query embeddings...")
    total_queries = NUM_QUERIES + WARMUP_QUERIES
    query_embeddings = _generate_random_embeddings(total_queries, DIMENSION)
    query_texts = [f"benchmark query number {i}" for i in range(total_queries)]

    # ------------------------------------------------------------------
    # 3. Benchmark raw FAISS search
    # ------------------------------------------------------------------
    print(f"\n[3/5] Benchmarking raw FAISS search...")
    # Warmup
    _ = benchmark_faiss_search(index, query_embeddings[:WARMUP_QUERIES])
    gc.collect()
    faiss_latencies = benchmark_faiss_search(index, query_embeddings[WARMUP_QUERIES:])
    _report("Raw FAISS Search (HNSW, 50k vectors)", faiss_latencies)

    # ------------------------------------------------------------------
    # 4. Benchmark RRF fusion
    # ------------------------------------------------------------------
    print(f"\n[4/5] Benchmarking RRF fusion...")
    # Simulate BM25 and dense results (20 results each, typical retrieval depth)
    rng = np.random.default_rng(42)
    bm25_results_list: list[list[tuple[str, float]]] = []
    dense_results_list: list[list[tuple[str, float]]] = []
    for _ in range(total_queries):
        bm25_ids = rng.choice(NUM_CHUNKS, size=20, replace=False)
        dense_ids = rng.choice(NUM_CHUNKS, size=20, replace=False)
        bm25_scores = sorted(rng.random(20), reverse=True)
        dense_scores = sorted(rng.random(20), reverse=True)
        bm25_results_list.append([(doc_ids[i], float(s)) for i, s in zip(bm25_ids, bm25_scores)])
        dense_results_list.append([(doc_ids[i], float(s)) for i, s in zip(dense_ids, dense_scores)])

    # Warmup
    _ = benchmark_rrf_fusion(bm25_results_list[:WARMUP_QUERIES], dense_results_list[:WARMUP_QUERIES])
    gc.collect()
    rrf_latencies = benchmark_rrf_fusion(
        bm25_results_list[WARMUP_QUERIES:], dense_results_list[WARMUP_QUERIES:]
    )
    _report("RRF Fusion (20+20 results)", rrf_latencies)

    # ------------------------------------------------------------------
    # 5. Benchmark full hybrid search pipeline
    # ------------------------------------------------------------------
    print(f"\n[5/5] Benchmarking full hybrid search pipeline...")
    with tempfile.TemporaryDirectory(prefix="desksearch_bench_") as tmpdir:
        tmppath = Path(tmpdir)
        config = Config(data_dir=tmppath / "data")
        config.data_dir.mkdir(parents=True, exist_ok=True)

        from desksearch.core.search import HybridSearchEngine

        engine = HybridSearchEngine(config, dimension=DIMENSION, cache_size=0)

        # Bulk-add documents
        print(f"  Adding {NUM_CHUNKS:,} documents to hybrid engine...")
        batch_size = 5000
        for start in range(0, NUM_CHUNKS, batch_size):
            end = min(start + batch_size, NUM_CHUNKS)
            batch = [
                (doc_ids[i], f"Document text for chunk {i} with some words", embeddings[i])
                for i in range(start, end)
            ]
            engine.add_documents(batch)
            if (start // batch_size) % 2 == 0:
                print(f"    {end:,}/{NUM_CHUNKS:,} docs added...")

        print(f"  Engine mode: {engine.mode}")
        print(f"  BM25 docs: {engine.bm25.doc_count:,}")
        print(f"  Dense docs: {engine.dense.doc_count:,}")

        # Warmup
        for i in range(WARMUP_QUERIES):
            engine.search_sync(
                query_texts[i], query_embeddings[i], top_k=TOP_K, max_snippets=0
            )
            if engine._cache:
                engine._cache.clear()

        gc.collect()

        hybrid_latencies = benchmark_hybrid_search(
            engine,
            query_embeddings[WARMUP_QUERIES:],
            query_texts[WARMUP_QUERIES:],
        )
        _report(f"Full Hybrid Search ({NUM_CHUNKS:,} chunks, no snippets)", hybrid_latencies)

        # Also benchmark with snippets
        print(f"\n  (Re-running with snippet extraction enabled...)")
        # Re-add a small set of longer texts for snippet testing
        for i in range(min(100, NUM_CHUNKS)):
            engine.set_doc_text(
                doc_ids[i],
                f"This is a longer document text for chunk {i}. "
                f"It contains multiple sentences about benchmark query topics. "
                f"The benchmark measures search speed and latency percentiles. "
                f"DeskSearch uses BM25 and dense retrieval for hybrid search."
            )

        snippet_latencies: list[float] = []
        for i in range(min(200, NUM_QUERIES)):
            if engine._cache:
                engine._cache.clear()
            t0 = time.perf_counter()
            engine.search_sync(
                query_texts[WARMUP_QUERIES + i],
                query_embeddings[WARMUP_QUERIES + i],
                top_k=TOP_K,
                max_snippets=3,
            )
            snippet_latencies.append((time.perf_counter() - t0) * 1000)

        _report(f"Hybrid Search + Snippets (200 queries)", snippet_latencies)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    p50_hybrid = _percentile(hybrid_latencies, 50)
    target = 5.0
    status = "✅ PASS" if p50_hybrid < target else "❌ FAIL"
    print(f"\n{'=' * 60}")
    print(f"  SUMMARY — Target: p50 < {target:.0f}ms")
    print(f"  Hybrid search p50: {p50_hybrid:.2f}ms  {status}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
