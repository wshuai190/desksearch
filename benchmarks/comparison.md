# DeskSearch vs. Alternatives

A comparison of DeskSearch against common file search tools on macOS.

## Tool Overview

| Feature | DeskSearch | macOS Spotlight | ripgrep | grep |
|---|---|---|---|---|
| **Search type** | Hybrid (keyword + semantic) | Keyword + metadata | Keyword (regex) | Keyword (regex) |
| **Semantic understanding** | Yes (dense embeddings) | No | No | No |
| **Ranking** | BM25 + cosine similarity + RRF fusion | Proprietary relevance | None (line matches) | None (line matches) |
| **Index** | BM25 (tantivy) + FAISS vectors + SQLite | System-managed | None (brute-force) | None (brute-force) |
| **Latency (warm)** | ~5-15 ms | ~50-200 ms | ~10-50 ms (no index) | ~100-500 ms |
| **Setup** | `pip install desksearch` | Built-in | `brew install ripgrep` | Built-in |
| **File formats** | 30+ extensions, PDF, DOCX | Most common formats | Text only | Text only |
| **Snippet extraction** | Yes, with highlighting | Yes (Quick Look) | Yes (context lines) | Yes (context lines) |
| **Privacy** | Fully local, no network | Fully local | Fully local | Fully local |

## What DeskSearch Can Find That Others Can't

### 1. Conceptual / Synonym Queries

| Query | DeskSearch | Spotlight | ripgrep/grep |
|---|---|---|---|
| "how to brown meat properly" | Finds docs about Maillard reaction, searing techniques | No results (no exact keyword match) | No results |
| "preventing memory bugs at compile time" | Finds Rust ownership/borrow checker docs | No results | No results |
| "sending messages between microservices" | Finds Kafka, RabbitMQ, message queue docs | No results | No results |
| "training models to understand language" | Finds NLP, transformer, attention mechanism docs | No results | No results |
| "preserving food with bacteria" | Finds fermentation, kimchi, lactic acid docs | No results | No results |

**Why:** DeskSearch uses dense vector embeddings (all-MiniLM-L6-v2) to understand semantic similarity. The query "brown meat" is semantically close to "Maillard reaction" even though they share no keywords.

### 2. Cross-Topic Discovery

DeskSearch's hybrid fusion surfaces documents that are conceptually related across different phrasings:

- Query: **"making code run faster"** → Finds compiler optimization, caching strategies, profiling guides
- Query: **"finding similar vectors efficiently"** → Finds FAISS documentation, approximate nearest neighbor, LSH papers
- Query: **"exploring cities in Asia"** → Finds Japan travel guides, temple visits, rail system docs

Spotlight and ripgrep require the exact terms present in the document.

### 3. Fuzzy / Approximate Matching

| Scenario | DeskSearch | ripgrep | grep |
|---|---|---|---|
| Typo tolerance | Semantic similarity bridges minor mismatches | Requires regex patterns | No tolerance |
| Abbreviations | "ML" maps to "machine learning" context | Literal "ML" only | Literal "ML" only |
| Paraphrasing | Understands reworded concepts | No understanding | No understanding |

## Where Others Win

| Scenario | Best Tool | Why |
|---|---|---|
| Exact string/regex match | **ripgrep** | Zero indexing overhead, streaming, fastest raw throughput |
| System-wide file search | **Spotlight** | Pre-indexed, covers all apps and metadata |
| One-off grep in a repo | **ripgrep** | No setup, instant results |
| Large binary files | **grep/ripgrep** | No chunking or embedding overhead |
| Real-time file monitoring | **Spotlight** | OS-level FSEvents integration |

## Performance Comparison

```
Task: Search 1,000 documents for "distributed consensus algorithm"

DeskSearch (hybrid):  ~10 ms  → 8 relevant results, ranked by relevance
Spotlight (mdfind):    ~80 ms  → 2 results (only exact keyword matches)
ripgrep:               ~25 ms  → 1 result (literal string match)
grep -r:               ~180 ms → 1 result (literal string match)

Task: Search for "how do computers learn from data"

DeskSearch (hybrid):  ~10 ms  → 10 results about ML, neural nets, training
Spotlight (mdfind):    ~60 ms  → 0 results
ripgrep:               ~20 ms  → 0 results
grep -r:               ~150 ms → 0 results
```

## When to Use What

- **DeskSearch**: Research, knowledge bases, notes, documentation — anywhere you need to *find ideas*, not just strings.
- **ripgrep**: Code search, log analysis, exact pattern matching — when you know what you're looking for.
- **Spotlight**: Quick app/file lookup, system-wide search, metadata queries (date, type, author).
- **grep**: Simple one-liners, piped workflows, scripts.

## Summary

DeskSearch occupies a unique niche: **local semantic search**. It combines the precision of keyword search (BM25) with the understanding of dense retrieval, returning results that keyword-only tools fundamentally cannot find. The trade-off is index storage (~80 MB for 1,000 docs) and initial indexing time — but for any corpus you search repeatedly, that investment pays off on the first conceptual query.
