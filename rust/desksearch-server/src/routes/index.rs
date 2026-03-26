//! Indexing endpoint: POST /api/index

use std::sync::Arc;
use std::time::Instant;

use axum::{
    extract::State,
    http::StatusCode,
    routing::post,
    Json, Router,
};
use serde::{Deserialize, Serialize};
use tracing::{info, warn};

use desksearch_indexer::{ChunkerConfig, FileWalker};
use desksearch_indexer::parsers;

use crate::state::AppState;

#[derive(Debug, Deserialize)]
pub struct IndexRequest {
    pub paths: Vec<String>,
}

#[derive(Debug, Serialize)]
pub struct IndexResponse {
    pub indexed: usize,
    pub skipped: usize,
    pub elapsed_ms: u64,
}

async fn index_handler(
    State(state): State<Arc<AppState>>,
    Json(req): Json<IndexRequest>,
) -> Result<Json<IndexResponse>, (StatusCode, String)> {
    let start = Instant::now();

    let roots: Vec<_> = req.paths.iter().map(std::path::PathBuf::from).collect();
    let walker = FileWalker::new(roots);
    let walk_result = walker.walk().map_err(|e| {
        (StatusCode::INTERNAL_SERVER_ERROR, format!("Walk failed: {e}"))
    })?;

    info!(
        "Walk found {} files ({} skipped) in {}ms",
        walk_result.files.len(),
        walk_result.skipped,
        walk_result.elapsed_ms
    );

    let chunker_config = ChunkerConfig::default();
    let mut indexed = 0usize;
    let mut skipped = walk_result.skipped;

    // Get a BM25 writer
    let bm25_writer = {
        let engine = state.search.read().unwrap();
        engine.bm25().writer(50)
    };
    let mut bm25_writer = bm25_writer.map_err(|e| {
        (StatusCode::INTERNAL_SERVER_ERROR, format!("BM25 writer failed: {e}"))
    })?;

    for file_path in &walk_result.files {
        let path_str = file_path.to_string_lossy();

        // Parse file content
        let text = match parsers::parse_file(file_path) {
            Ok(Some(text)) => text,
            Ok(None) => {
                skipped += 1;
                continue;
            }
            Err(e) => {
                warn!("Failed to parse {}: {e}", path_str);
                skipped += 1;
                continue;
            }
        };

        // Get file metadata
        let metadata = std::fs::metadata(file_path).ok();
        let file_name = file_path
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default();
        let extension = file_path
            .extension()
            .map(|e| e.to_string_lossy().to_string())
            .unwrap_or_default();
        let size_bytes = metadata.as_ref().map(|m| m.len() as i64).unwrap_or(0);
        let modified_time = metadata
            .as_ref()
            .and_then(|m| m.modified().ok())
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_secs_f64())
            .unwrap_or(0.0);

        // Compute a simple content hash
        let content_hash = format!("{:x}", md5_hash(text.as_bytes()));

        // Chunk the text
        let chunks = desksearch_indexer::chunker::chunk_text(&text, &chunker_config);

        // Store in metadata DB and BM25 index
        let store = state.store.lock().unwrap();

        // Check if file needs reindexing
        if !store.needs_reindex(&path_str, &content_hash).unwrap_or(true) {
            continue;
        }

        let doc_id = store
            .upsert_file(&path_str, &file_name, &extension, size_bytes, &content_hash, modified_time)
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, format!("DB upsert failed: {e}")))?;

        // Delete old chunks before inserting new ones
        let _ = store.delete_chunks_for_doc(doc_id);

        // Delete old BM25 entries for this path
        let engine = state.search.read().unwrap();
        engine.bm25().delete_by_path(&mut bm25_writer, &path_str);

        for chunk in &chunks {
            let chunk_id = store
                .insert_chunk(doc_id, chunk.index as i64, &chunk.text, chunk.offset as i64)
                .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, format!("Chunk insert failed: {e}")))?;

            engine
                .bm25()
                .add_chunk(&mut bm25_writer, chunk_id as u64, &chunk.text, &path_str)
                .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, format!("BM25 add failed: {e}")))?;
        }

        drop(engine);
        drop(store);

        indexed += 1;
    }

    // Commit BM25 writer
    bm25_writer.commit().map_err(|e| {
        (StatusCode::INTERNAL_SERVER_ERROR, format!("BM25 commit failed: {e}"))
    })?;

    let elapsed_ms = start.elapsed().as_millis() as u64;
    info!("Indexed {indexed} files ({skipped} skipped) in {elapsed_ms}ms");

    Ok(Json(IndexResponse {
        indexed,
        skipped,
        elapsed_ms,
    }))
}

/// Simple hash for content deduplication (not cryptographic).
fn md5_hash(data: &[u8]) -> u64 {
    use std::hash::{Hash, Hasher};
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    data.hash(&mut hasher);
    hasher.finish()
}

pub fn router() -> Router<Arc<AppState>> {
    Router::new().route("/index", post(index_handler))
}
