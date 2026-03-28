"""Smart document collections using embedding-based clustering.

Groups documents into topics using k-means clustering on document-level
embeddings (average of chunk embeddings). All computation is local — no
external API calls.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Maximum number of topics to auto-discover
MAX_TOPICS = 12
MIN_DOCS_PER_TOPIC = 2


@dataclass
class Topic:
    """A document cluster / topic."""
    id: int
    label: str
    doc_ids: list[int]
    doc_paths: list[str]
    doc_filenames: list[str]
    keywords: list[str] = field(default_factory=list)
    centroid: Optional[np.ndarray] = field(default=None, repr=False)


def build_doc_embeddings(
    store,
    emb_path,
) -> tuple[dict[int, np.ndarray], dict[int, str], dict[int, str]]:
    """Build per-document embeddings by averaging chunk embeddings.

    Returns:
        doc_embeddings: {doc_id -> mean_embedding}
        doc_paths: {doc_id -> path}
        doc_filenames: {doc_id -> filename}
    """
    import numpy as np
    from pathlib import Path

    emb_file = emb_path / "embeddings.npy"
    ids_file = emb_path / "chunk_ids.npy"

    if not emb_file.exists() or not ids_file.exists():
        return {}, {}, {}

    embeddings = np.load(str(emb_file)).astype(np.float32)
    chunk_ids = np.load(str(ids_file))

    # Build chunk_id → embedding lookup
    chunk_emb_map: dict[int, np.ndarray] = {}
    for i, cid in enumerate(chunk_ids):
        if i < len(embeddings):
            chunk_emb_map[int(cid)] = embeddings[i]

    if not chunk_emb_map:
        return {}, {}, {}

    # For each doc, average its chunk embeddings
    docs = store.all_documents()
    doc_embeddings: dict[int, np.ndarray] = {}
    doc_paths: dict[int, str] = {}
    doc_filenames: dict[int, str] = {}

    for doc in docs:
        chunks = store.get_chunks(doc.id)
        if not chunks:
            continue
        chunk_vecs = [chunk_emb_map[c.id] for c in chunks if c.id in chunk_emb_map]
        if not chunk_vecs:
            continue
        doc_embeddings[doc.id] = np.mean(chunk_vecs, axis=0)
        doc_paths[doc.id] = doc.path
        doc_filenames[doc.id] = doc.filename

    return doc_embeddings, doc_paths, doc_filenames


def cluster_documents(
    doc_embeddings: dict[int, np.ndarray],
    doc_paths: dict[int, str],
    doc_filenames: dict[int, str],
    n_clusters: Optional[int] = None,
) -> list[Topic]:
    """Cluster documents into topics using k-means.

    Args:
        doc_embeddings: {doc_id -> embedding vector}
        doc_paths: {doc_id -> path}
        doc_filenames: {doc_id -> filename}
        n_clusters: Number of clusters. If None, auto-selected.

    Returns:
        List of Topic objects.
    """
    if len(doc_embeddings) < MIN_DOCS_PER_TOPIC * 2:
        return []

    doc_ids = list(doc_embeddings.keys())
    X = np.stack([doc_embeddings[d] for d in doc_ids]).astype(np.float32)

    # Normalize embeddings for cosine similarity
    norms = np.linalg.norm(X, axis=1, keepdims=True) + 1e-8
    X_norm = X / norms

    # Auto-select number of clusters
    n = len(doc_ids)
    if n_clusters is None:
        # Heuristic: sqrt(n/2) capped at MAX_TOPICS, minimum 2
        n_clusters = max(2, min(MAX_TOPICS, int(math.sqrt(n / 2))))

    try:
        from sklearn.cluster import KMeans
        km = KMeans(
            n_clusters=n_clusters,
            random_state=42,
            n_init=10,
            max_iter=100,
        )
        labels = km.fit_predict(X_norm)
        centroids = km.cluster_centers_
    except ImportError:
        logger.warning("scikit-learn not available, using simple centroid clustering")
        labels, centroids = _simple_kmeans(X_norm, n_clusters)

    # Build topics
    topics: list[Topic] = []
    for cluster_id in range(n_clusters):
        mask = labels == cluster_id
        if mask.sum() < 1:
            continue
        cluster_doc_ids = [doc_ids[i] for i in range(len(doc_ids)) if mask[i]]
        cluster_paths = [doc_paths[d] for d in cluster_doc_ids]
        cluster_fnames = [doc_filenames[d] for d in cluster_doc_ids]

        if len(cluster_doc_ids) < 1:
            continue

        # Generate a label from common filename words
        label = _generate_topic_label(cluster_fnames, cluster_id)
        centroid = centroids[cluster_id] if centroids is not None else None

        topics.append(Topic(
            id=cluster_id,
            label=label,
            doc_ids=cluster_doc_ids,
            doc_paths=cluster_paths,
            doc_filenames=cluster_fnames,
            centroid=centroid,
        ))

    # Sort by size descending
    topics.sort(key=lambda t: len(t.doc_ids), reverse=True)
    return topics


def find_duplicates(
    doc_embeddings: dict[int, np.ndarray],
    doc_paths: dict[int, str],
    doc_filenames: dict[int, str],
    threshold: float = 0.92,
) -> list[dict]:
    """Find document pairs with very similar content (potential duplicates).

    Uses cosine similarity on document embeddings. Returns pairs above threshold.

    Args:
        doc_embeddings: {doc_id -> embedding}
        threshold: Similarity threshold (default 0.92 = ~92% similar)

    Returns:
        List of {doc_a, doc_b, similarity, path_a, path_b, filename_a, filename_b}
    """
    if len(doc_embeddings) < 2:
        return []

    doc_ids = list(doc_embeddings.keys())
    X = np.stack([doc_embeddings[d] for d in doc_ids]).astype(np.float32)

    # Normalize for cosine similarity
    norms = np.linalg.norm(X, axis=1, keepdims=True) + 1e-8
    X_norm = X / norms

    # Compute pairwise similarities (O(n²) but fine for <10k docs)
    sim_matrix = X_norm @ X_norm.T

    duplicates: list[dict] = []
    n = len(doc_ids)
    for i in range(n):
        for j in range(i + 1, n):
            sim = float(sim_matrix[i, j])
            if sim >= threshold:
                doc_a = doc_ids[i]
                doc_b = doc_ids[j]
                # Skip if same file at different paths (unlikely but possible)
                if doc_paths.get(doc_a) == doc_paths.get(doc_b):
                    continue
                duplicates.append({
                    "doc_id_a": doc_a,
                    "doc_id_b": doc_b,
                    "similarity": round(sim, 4),
                    "path_a": doc_paths.get(doc_a, ""),
                    "path_b": doc_paths.get(doc_b, ""),
                    "filename_a": doc_filenames.get(doc_a, ""),
                    "filename_b": doc_filenames.get(doc_b, ""),
                })

    # Sort by similarity descending
    duplicates.sort(key=lambda x: x["similarity"], reverse=True)
    return duplicates[:50]  # cap at 50 pairs


def find_related_docs(
    target_doc_id: int,
    doc_embeddings: dict[int, np.ndarray],
    doc_paths: dict[int, str],
    doc_filenames: dict[int, str],
    top_k: int = 5,
) -> list[dict]:
    """Find documents most similar to a target document.

    Args:
        target_doc_id: The doc_id to find similar docs for
        doc_embeddings: {doc_id -> embedding}
        top_k: Number of similar docs to return

    Returns:
        List of {doc_id, similarity, path, filename}
    """
    if target_doc_id not in doc_embeddings or len(doc_embeddings) < 2:
        return []

    target_emb = doc_embeddings[target_doc_id]
    target_norm = target_emb / (np.linalg.norm(target_emb) + 1e-8)

    results: list[tuple[int, float]] = []
    for doc_id, emb in doc_embeddings.items():
        if doc_id == target_doc_id:
            continue
        emb_norm = emb / (np.linalg.norm(emb) + 1e-8)
        sim = float(np.dot(target_norm, emb_norm))
        results.append((doc_id, sim))

    results.sort(key=lambda x: x[1], reverse=True)

    return [
        {
            "doc_id": doc_id,
            "similarity": round(sim, 4),
            "path": doc_paths.get(doc_id, ""),
            "filename": doc_filenames.get(doc_id, ""),
        }
        for doc_id, sim in results[:top_k]
        if sim > 0.3  # minimum relevance threshold
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_topic_label(filenames: list[str], cluster_id: int) -> str:
    """Generate a human-readable topic label from filenames."""
    import re
    from collections import Counter

    # Extract words from filenames (split on spaces, dashes, underscores)
    words: list[str] = []
    for fname in filenames:
        # Remove extension
        name = re.sub(r"\.[^.]+$", "", fname)
        # Split on non-alphanumeric
        parts = re.split(r"[^a-zA-Z0-9]+", name)
        words.extend(w.lower() for w in parts if len(w) >= 3)

    # Filter stopwords and count
    noise = {"the", "and", "for", "from", "with", "that", "this", "doc", "file",
             "new", "old", "copy", "final", "draft", "version", "rev", "tmp"}
    content = [w for w in words if w not in noise and not w.isdigit()]
    if not content:
        return f"Topic {cluster_id + 1}"

    counter = Counter(content)
    top_words = [w for w, _ in counter.most_common(3)]
    return " / ".join(w.capitalize() for w in top_words[:2]) or f"Topic {cluster_id + 1}"


def _simple_kmeans(
    X: np.ndarray,
    k: int,
    max_iter: int = 50,
) -> tuple[np.ndarray, Optional[np.ndarray]]:
    """Minimal k-means fallback (no sklearn needed)."""
    n = len(X)
    if n <= k:
        return np.arange(n), X.copy()

    # Random initialization
    rng = np.random.default_rng(42)
    indices = rng.choice(n, size=k, replace=False)
    centroids = X[indices].copy()

    labels = np.zeros(n, dtype=int)
    for _ in range(max_iter):
        # Assignment
        sims = X @ centroids.T
        new_labels = np.argmax(sims, axis=1)
        if np.all(new_labels == labels):
            break
        labels = new_labels
        # Update centroids
        for c in range(k):
            mask = labels == c
            if mask.any():
                centroids[c] = X[mask].mean(axis=0)
                norm = np.linalg.norm(centroids[c])
                if norm > 0:
                    centroids[c] /= norm

    return labels, centroids
