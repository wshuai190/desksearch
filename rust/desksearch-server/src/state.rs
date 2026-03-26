//! Application state shared across all request handlers.

use std::path::{Path, PathBuf};
use std::sync::{Mutex, RwLock};
use std::time::Instant;

use anyhow::Result;
use desksearch_core::{EmbedClient, SearchConfig, SearchEngine, VectorIndex};
use desksearch_indexer::MetadataStore;
use tracing::{info, warn};

use crate::config::DeskSearchConfig;

/// Shared application state.
///
/// Note: MetadataStore uses Mutex (not RwLock) because rusqlite::Connection
/// is !Sync. For search, RwLock is fine since tantivy handles its own locking.
pub struct AppState {
    /// The search engine instance.
    pub search: RwLock<SearchEngine>,
    /// Metadata store for file/chunk info (Mutex because rusqlite is !Sync).
    pub store: Mutex<MetadataStore>,
    /// Optional embed client for dense search.
    pub embed_client: Option<Mutex<EmbedClient>>,
    /// Server start time (for uptime calculation).
    pub start_time: Instant,
    /// Path to config file (~/.desksearch/config.json).
    pub config_path: PathBuf,
    /// Project root directory (for finding scripts, venv, etc.).
    #[allow(dead_code)]
    pub project_root: PathBuf,
}

impl AppState {
    /// Create a new AppState, initializing search engine and metadata store.
    /// `project_root` is used to find the Python venv and embed script.
    pub fn new(data_dir: &Path, project_root: &Path, config: &DeskSearchConfig) -> Result<Self> {
        std::fs::create_dir_all(data_dir)?;

        let index_dir = data_dir.join("index");
        let db_path = data_dir.join("metadata.db");
        let config_path = data_dir.join("config.json");

        let store = MetadataStore::open(&db_path)?;

        // Try to set up embedding infrastructure
        let python_path = project_root.join(".venv/bin/python3");
        let script_path = project_root.join("scripts/embed_server.py");
        let vector_path = data_dir.join("vectors.usearch");

        let (embed_client, vector_index) = if python_path.exists() && script_path.exists() {
            info!("Found Python venv and embed script, initializing embedding...");
            match EmbedClient::new(
                python_path.to_str().unwrap_or("python3"),
                script_path.to_str().unwrap_or(""),
                config.embedding_dim,
                config.embedding_layers,
            ) {
                Ok(mut client) => {
                    match client.ping() {
                        Ok(()) => {
                            info!("EmbedClient ready (dim={}, layers={})", config.embedding_dim, config.embedding_layers);
                            match VectorIndex::open_or_create(&vector_path, config.embedding_dim) {
                                Ok(vi) => {
                                    info!("VectorIndex ready at {}", vector_path.display());
                                    (Some(client), Some(vi))
                                }
                                Err(e) => {
                                    warn!("Failed to create VectorIndex: {e}, continuing BM25-only");
                                    (Some(client), None)
                                }
                            }
                        }
                        Err(e) => {
                            warn!("EmbedClient ping failed: {e}, continuing BM25-only");
                            (None, None)
                        }
                    }
                }
                Err(e) => {
                    warn!("Failed to create EmbedClient: {e}, continuing BM25-only");
                    (None, None)
                }
            }
        } else {
            if !python_path.exists() {
                info!("Python venv not found at {}, BM25-only mode", python_path.display());
            }
            if !script_path.exists() {
                info!("Embed script not found at {}, BM25-only mode", script_path.display());
            }
            (None, None)
        };

        // Create search engine — hybrid if vector index is available
        let search = if let Some(vi) = vector_index {
            info!("Creating hybrid search engine (BM25 + dense)");
            SearchEngine::new_hybrid(&index_dir, SearchConfig::default(), vi)?
        } else {
            info!("Creating BM25-only search engine");
            SearchEngine::new(&index_dir, SearchConfig::default())?
        };

        Ok(Self {
            search: RwLock::new(search),
            store: Mutex::new(store),
            embed_client: embed_client.map(Mutex::new),
            start_time: Instant::now(),
            config_path,
            project_root: project_root.to_path_buf(),
        })
    }
}
