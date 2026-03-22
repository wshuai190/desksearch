# DeskSearch Benchmark Results

**Date:** 2026-03-22 22:22:20
**Platform:** darwin / Python 3.12.13
**CPU:** 8 cores (8 logical)
**RAM:** 8 GB

## 1. Indexing Speed

| Corpus Size | Time | Files/sec | Chunks/sec | Peak Memory |
|---|---|---|---|---|
| 1000 files (2893 chunks) | 44.12 s | 22.7 | 65.6 | 595.4 MB |
| 100 files (288 chunks) | 5.15 s | 19.4 | 56.0 | 656.4 MB |
| 500 files (1495 chunks) | 22.56 s | 22.2 | 66.3 | 739.9 MB |

## 2. Search Latency

- **Cold start** (model load + first query): **588.6 ms**
- **Warm search** (50 queries):

| Metric | Value |
|---|---|
| AVG MS | 1.51 ms |
| P50 MS | 1.46 ms |
| P95 MS | 2.0 ms |
| P99 MS | 2.1 ms |
| MIN MS | 1.21 ms |
| MAX MS | 2.16 ms |
| QPS | **660.3 queries/sec** |

## 3. Memory Footprint

| State | RSS |
|---|---|
| Idle (no model) | 59.2 MB |
| Model loaded | 261.7 MB |
| During indexing | 284.0 MB |
| After cooldown | 427.1 MB |

- Model overhead: **202.5 MB**
- Memory reclaimed after cooldown: **-143.1 MB**

## 4. Index Size

**Corpus:** 1001 documents, 2895 chunks, 0.82 MB on disk

| Component | Size |
|---|---|
| BM25 (tantivy) | 2.02 MB |
| Dense (FAISS) | 4.35 MB |
| SQLite metadata | 1.38 MB |
| Embeddings (.npy) | 4.26 MB |
| **Total index** | **12.0 MB** |

**Index-to-corpus ratio:** 14.57x

## 5. Search Quality (Precision@5 / Recall@5)

| Mode | Alpha | Precision@5 | Recall@5 |
|---|---|---|---|
| Bm25 Only | 0.0 | **0.920** | 0.875 |
| Dense Only | 1.0 | **0.850** | 0.875 |
| Hybrid | 0.5 | **0.860** | 0.950 |

> **Hybrid achieves the best recall** (0.950) vs BM25 (0.875) and dense (0.875) — it finds relevant categories more consistently by combining both signals. Precision: hybrid 0.860, BM25 0.920, dense 0.850.

### Test Queries

| # | Query | Expected Category |
|---|---|---|
| 1 | Maillard reaction amino acids sugars | cooking |
| 2 | Rust ownership borrow checker | programming |
| 3 | Kafka message queue asynchronous | systems |
| 4 | attention mechanism transformer | research |
| 5 | gradient descent backpropagation | machine_learning |
| 6 | Japan rail system Shinkansen | travel |
| 7 | fermentation kimchi sauerkraut | cooking |
| 8 | Python garbage collection memory | programming |
| 9 | load balancer distributed system | systems |
| 10 | convolutional neural network image | machine_learning |
| 11 | how to brown meat properly | cooking |
| 12 | preventing memory bugs at compile time | programming |
| 13 | sending messages between microservices | systems |
| 14 | training models to understand language | research, machine_learning |
| 15 | exploring cities in Asia | travel |
| 16 | preserving food with bacteria | cooking |
| 17 | finding similar vectors efficiently | research, machine_learning |
| 18 | making code run faster | programming, systems |
| 19 | booking accommodation abroad | travel |
| 20 | scientific paper writing methodology | research |
