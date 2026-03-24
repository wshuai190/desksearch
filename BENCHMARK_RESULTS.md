# DeskSearch Benchmark Results — Sprint Mar 25, 2026

## Baseline (12:00am)
| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Raw FAISS search p50 (50k, 64d HNSW) | 0.08ms | <1ms | ✅ |
| RRF fusion p50 (20+20 results) | 0.04ms | <0.5ms | ✅ |
| Hybrid search p50 (50k, no snippets) | 1.11ms | <5ms | ✅ |
| Hybrid search + snippets p50 | 1.09ms | <5ms | ✅ |
| Hybrid search QPS | 896/sec | >200 | ✅ |
| Test count | 237 | 180+ | ✅ |
| Indexing speed | TBD | 100+ files/sec | ❓ |
| Startup time | TBD | <3s | ❓ |
| Memory idle | TBD | <150MB | ❓ |
| Memory peak | TBD | <400MB | ❓ |
| Disk per 1000 docs | TBD | <5MB | ❓ |
| App bundle size | TBD | <150MB | ❓ |
| Frontend bundle | ~92KB gzip | <100KB | ✅ |

## Phase Notes
- Search speed already exceeds target (p50 1.11ms vs 5ms target)
- Starbucks 2D Matryoshka: 4 layers, 64d (regular tier)
- FAISS HNSW M=32, efSearch=32
- All 237 tests pass (segfault fix applied: mock embedder for API tests)
