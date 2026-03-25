//! Application state shared across all request handlers.

use std::path::Path;
use std::sync::{Mutex, RwLock};

use anyhow::Result;
use desksearch_core::{SearchEngine, SearchConfig};
use desksearch_indexer::MetadataStore;

/// Shared application state.
///
/// Note: MetadataStore uses Mutex (not RwLock) because rusqlite::Connection
/// is !Sync. For search, RwLock is fine since tantivy handles its own locking.
pub struct AppState {
    /// The search engine instance.
    pub search: RwLock<SearchEngine>,
    /// Metadata store for file/chunk info (Mutex because rusqlite is !Sync).
    pub store: Mutex<MetadataStore>,
}

impl AppState {
    /// Create a new AppState, initializing search engine and metadata store.
    pub fn new(data_dir: &Path) -> Result<Self> {
        std::fs::create_dir_all(data_dir)?;

        let index_dir = data_dir.join("index");
        let db_path = data_dir.join("metadata.db");

        let search = SearchEngine::new(&index_dir, SearchConfig::default())?;
        let store = MetadataStore::open(&db_path)?;

        Ok(Self {
            search: RwLock::new(search),
            store: Mutex::new(store),
        })
    }
}
