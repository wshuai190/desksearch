# DeskSearch Benchmark Results — v0.5.0

## Search Performance (50k chunks, 64d Starbucks HNSW)

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Raw FAISS search p50 | 0.09ms | <1ms | ✅ |
| Raw FAISS QPS | 11,340/sec | — | — |
| RRF fusion p50 | 0.04ms | <0.5ms | ✅ |
| Hybrid search p50 (no snippets) | **0.83ms** | <5ms | ✅ |
| Hybrid search p95 | 0.90ms | <10ms | ✅ |
| Hybrid search p99 | 0.99ms | <20ms | ✅ |
| Hybrid + snippets p50 | 0.83ms | <5ms | ✅ |
| Hybrid QPS | **1,193/sec** | >200 | ✅ |

## Test Suite
| Metric | Value |
|--------|-------|
| Total tests | 251 |
| Pass rate | 100% |
| Test time | ~70s |

## Architecture
- **Model:** Starbucks 2D Matryoshka (ielabgroup/Starbucks-msmarco)
- **Tier:** Regular (4 layers, 64d)
- **FAISS:** IndexIDMap2 + HNSW (M=32, efSearch=32)
- **BM25:** tantivy
- **Fusion:** Weighted RRF (α=0.4, k=60)
- **Platform:** macOS arm64 (Apple M-series)
