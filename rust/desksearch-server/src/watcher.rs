//! File watcher — monitors folders and triggers reindexing on changes.

use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use notify::{RecommendedWatcher, RecursiveMode, Watcher, EventKind};
use tokio::sync::mpsc;
use tracing::{info, warn, error};

use desksearch_indexer::{ChunkerConfig, parsers};

use crate::state::AppState;

/// Spawn a file watcher task that monitors the given folders.
/// Returns a JoinHandle that can be used to await completion.
pub fn spawn_watcher(
    state: Arc<AppState>,
    folders: Vec<String>,
) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        if folders.is_empty() {
            info!("No folders to watch");
            return;
        }

        let (tx, mut rx) = mpsc::channel::<PathBuf>(256);

        // Create the watcher in a blocking thread since notify uses sync callbacks
        let _watcher = {
            let tx = tx.clone();
            let folders = folders.clone();
            tokio::task::spawn_blocking(move || -> Option<RecommendedWatcher> {
                let tx = tx;
                let mut watcher = match notify::recommended_watcher(move |res: Result<notify::Event, notify::Error>| {
                    if let Ok(event) = res {
                        match event.kind {
                            EventKind::Create(_) | EventKind::Modify(_) | EventKind::Remove(_) => {
                                for path in event.paths {
                                    let _ = tx.blocking_send(path);
                                }
                            }
                            _ => {}
                        }
                    }
                }) {
                    Ok(w) => w,
                    Err(e) => {
                        error!("Failed to create file watcher: {e}");
                        return None;
                    }
                };

                for folder in &folders {
                    let path = PathBuf::from(folder);
                    if path.exists() {
                        if let Err(e) = watcher.watch(&path, RecursiveMode::Recursive) {
                            warn!("Failed to watch {folder}: {e}");
                        } else {
                            info!("Watching folder: {folder}");
                        }
                    } else {
                        warn!("Watch folder does not exist: {folder}");
                    }
                }

                Some(watcher)
            })
            .await
        };

        info!("File watcher started for {} folders", folders.len());

        // Debounce: collect changes over 2 seconds, then reindex
        let mut pending: std::collections::HashSet<PathBuf> = std::collections::HashSet::new();
        let debounce = Duration::from_secs(2);

        loop {
            tokio::select! {
                Some(path) = rx.recv() => {
                    pending.insert(path);
                    // Drain any additional events that arrived
                    while let Ok(path) = rx.try_recv() {
                        pending.insert(path);
                    }
                    // Wait for debounce period
                    tokio::time::sleep(debounce).await;
                    // Drain again after sleep
                    while let Ok(path) = rx.try_recv() {
                        pending.insert(path);
                    }

                    let paths: Vec<PathBuf> = pending.drain().collect();
                    if !paths.is_empty() {
                        reindex_files(&state, &paths);
                    }
                }
                else => break,
            }
        }
    })
}

fn reindex_files(state: &AppState, paths: &[PathBuf]) {
    let chunker_config = ChunkerConfig::default();

    let bm25_writer = {
        let engine = state.search.read().unwrap();
        engine.bm25().writer(50)
    };
    let mut bm25_writer = match bm25_writer {
        Ok(w) => w,
        Err(e) => {
            error!("Failed to create BM25 writer for reindex: {e}");
            return;
        }
    };

    let mut reindexed = 0usize;

    for file_path in paths {
        if !file_path.is_file() {
            // File was deleted — remove from all indices
            let path_str = file_path.to_string_lossy();
            let store = state.store.lock().unwrap();
            // Remove old vectors for this file's chunks
            if let Ok(old_chunk_ids) = store.get_chunk_ids_for_file(&path_str) {
                let engine = state.search.read().unwrap();
                for cid in &old_chunk_ids {
                    let _ = engine.remove_vector(*cid as u64);
                }
            }
            store.delete_file(&path_str).ok();
            drop(store);
            let engine = state.search.read().unwrap();
            engine.bm25().delete_by_path(&mut bm25_writer, &path_str);
            continue;
        }

        let path_str = file_path.to_string_lossy();

        let text = match parsers::parse_file(file_path) {
            Ok(Some(text)) => text,
            _ => continue,
        };

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

        let content_hash = {
            use std::hash::{Hash, Hasher};
            let mut hasher = std::collections::hash_map::DefaultHasher::new();
            text.as_bytes().hash(&mut hasher);
            format!("{:x}", hasher.finish())
        };

        let store = state.store.lock().unwrap();

        if !store.needs_reindex(&path_str, &content_hash).unwrap_or(true) {
            continue;
        }

        // Remove old vectors for this file's chunks before re-indexing
        if let Ok(old_chunk_ids) = store.get_chunk_ids_for_file(&path_str) {
            let engine = state.search.read().unwrap();
            for cid in &old_chunk_ids {
                let _ = engine.remove_vector(*cid as u64);
            }
        }

        let doc_id = match store.upsert_file(&path_str, &file_name, &extension, size_bytes, &content_hash, modified_time) {
            Ok(id) => id,
            Err(e) => {
                warn!("Failed to upsert file {}: {e}", path_str);
                continue;
            }
        };

        let _ = store.delete_chunks_for_doc(doc_id);
        let engine = state.search.read().unwrap();
        engine.bm25().delete_by_path(&mut bm25_writer, &path_str);

        let chunks = desksearch_indexer::chunker::chunk_text(&text, &chunker_config);

        // Collect chunk texts for batch embedding
        let mut chunk_ids = Vec::new();
        for chunk in &chunks {
            match store.insert_chunk(doc_id, chunk.index as i64, &chunk.text, chunk.offset as i64) {
                Ok(chunk_id) => {
                    let _ = engine.bm25().add_chunk(&mut bm25_writer, chunk_id as u64, &chunk.text, &path_str);
                    chunk_ids.push(chunk_id as u64);
                }
                Err(e) => warn!("Failed to insert chunk: {e}"),
            }
        }

        // Embed chunks if embed_client is available
        if let Some(ref embed_client) = state.embed_client {
            let texts: Vec<String> = chunks.iter().map(|c| c.text.clone()).collect();
            if let Ok(mut client) = embed_client.lock() {
                match client.embed(&texts) {
                    Ok(embeddings) => {
                        let engine = state.search.read().unwrap();
                        for (chunk_id, embedding) in chunk_ids.iter().zip(embeddings.iter()) {
                            let _ = engine.add_vector(*chunk_id, embedding);
                        }
                    }
                    Err(e) => warn!("Embedding failed during watcher reindex: {e}"),
                }
            }
        }

        drop(engine);
        drop(store);

        reindexed += 1;
    }

    if let Err(e) = bm25_writer.commit() {
        error!("Failed to commit BM25 during reindex: {e}");
    }

    // Save vectors if we embedded anything
    if reindexed > 0 {
        let engine = state.search.read().unwrap();
        if engine.has_dense() {
            let _ = engine.save_vectors();
        }
    }

    if reindexed > 0 {
        info!("Watcher reindexed {reindexed} files");
    }
}
