//! Application state shared across all request handlers.

use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, RwLock};
use std::time::Instant;

use anyhow::Result;
use desksearch_core::{EmbedClient, OnnxEmbedder, SearchConfig, SearchEngine, VectorIndex};
use desksearch_indexer::MetadataStore;
use tracing::{info, warn};

use crate::config::DeskSearchConfig;

/// Abstraction over embedding backends.
pub enum EmbedBackend {
    /// Native ONNX inference (preferred).
    Onnx(Arc<OnnxEmbedder>),
    /// Python subprocess fallback.
    Python(Mutex<EmbedClient>),
}

impl EmbedBackend {
    /// Embed a batch of texts.
    pub fn embed(&self, texts: &[String]) -> Result<Vec<Vec<f32>>> {
        match self {
            EmbedBackend::Onnx(embedder) => {
                let refs: Vec<&str> = texts.iter().map(|s| s.as_str()).collect();
                embedder.embed_batch(&refs)
            }
            EmbedBackend::Python(client) => {
                let mut client = client.lock().map_err(|e| anyhow::anyhow!("lock poisoned: {e}"))?;
                client.embed(texts)
            }
        }
    }

    /// Embed a single query string.
    pub fn embed_query(&self, query: &str) -> Result<Vec<f32>> {
        match self {
            EmbedBackend::Onnx(embedder) => embedder.embed_single(query),
            EmbedBackend::Python(client) => {
                let mut client = client.lock().map_err(|e| anyhow::anyhow!("lock poisoned: {e}"))?;
                client.embed_query(query)
            }
        }
    }

    /// Human-readable backend name for logging.
    pub fn name(&self) -> &'static str {
        match self {
            EmbedBackend::Onnx(_) => "onnx",
            EmbedBackend::Python(_) => "python",
        }
    }
}

/// Shared application state.
///
/// Note: MetadataStore uses Mutex (not RwLock) because rusqlite::Connection
/// is !Sync. For search, RwLock is fine since tantivy handles its own locking.
pub struct AppState {
    /// The search engine instance.
    pub search: RwLock<SearchEngine>,
    /// Metadata store for file/chunk info (Mutex because rusqlite is !Sync).
    pub store: Mutex<MetadataStore>,
    /// Optional embedding backend (ONNX or Python).
    pub embed_backend: Option<EmbedBackend>,
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

        let vector_path = data_dir.join("vectors.usearch");

        // --- Try ONNX backend first ---
        let onnx_backend = try_onnx_backend(config);

        // --- Fall back to Python subprocess ---
        let embed_backend = if let Some(backend) = onnx_backend {
            Some(backend)
        } else {
            try_python_backend(project_root, config)
        };

        if let Some(ref backend) = embed_backend {
            info!(backend = backend.name(), "embedding backend active");
        } else {
            info!("no embedding backend available, BM25-only mode");
        }

        // Set up VectorIndex if we have any embedding backend
        let vector_index = if embed_backend.is_some() {
            match VectorIndex::open_or_create(&vector_path, config.embedding_dim) {
                Ok(vi) => {
                    info!("VectorIndex ready at {}", vector_path.display());
                    Some(vi)
                }
                Err(e) => {
                    warn!("Failed to create VectorIndex: {e}, continuing BM25-only");
                    None
                }
            }
        } else {
            None
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
            embed_backend,
            start_time: Instant::now(),
            config_path,
            project_root: project_root.to_path_buf(),
        })
    }
}

/// Attempt to create the ONNX embedding backend.
fn try_onnx_backend(config: &DeskSearchConfig) -> Option<EmbedBackend> {
    let home = dirs_next::home_dir()?;
    let models_dir = home.join(".desksearch").join("models");

    // Map search_speed to model variant
    let variant = match config.search_speed.as_str() {
        "fast" => "fast",
        "precise" => "pro",
        _ => "regular", // "balanced" or anything else
    };

    let model_path = models_dir.join(format!("starbucks-{variant}.onnx"));
    let tokenizer_path = models_dir.join("tokenizer.json");

    if !model_path.exists() {
        info!(
            "ONNX model not found at {}, will try Python fallback",
            model_path.display()
        );
        return None;
    }
    if !tokenizer_path.exists() {
        info!(
            "Tokenizer not found at {}, will try Python fallback",
            tokenizer_path.display()
        );
        return None;
    }

    match OnnxEmbedder::new(&model_path, &tokenizer_path, config.embedding_dim) {
        Ok(embedder) => {
            info!(
                variant,
                dim = config.embedding_dim,
                "ONNX embedding backend ready"
            );
            Some(EmbedBackend::Onnx(Arc::new(embedder)))
        }
        Err(e) => {
            warn!("Failed to load ONNX model: {e}, will try Python fallback");
            None
        }
    }
}

/// Attempt to create the Python subprocess embedding backend.
fn try_python_backend(project_root: &Path, config: &DeskSearchConfig) -> Option<EmbedBackend> {
    let python_path = project_root.join(".venv/bin/python3");
    let script_path = project_root.join("scripts/embed_server.py");

    if !python_path.exists() {
        info!(
            "Python venv not found at {}, BM25-only mode",
            python_path.display()
        );
        return None;
    }
    if !script_path.exists() {
        info!(
            "Embed script not found at {}, BM25-only mode",
            script_path.display()
        );
        return None;
    }

    info!("Found Python venv and embed script, initializing embedding...");
    match EmbedClient::new(
        python_path.to_str().unwrap_or("python3"),
        script_path.to_str().unwrap_or(""),
        config.embedding_dim,
        config.embedding_layers,
    ) {
        Ok(mut client) => match client.ping() {
            Ok(()) => {
                info!(
                    dim = config.embedding_dim,
                    layers = config.embedding_layers,
                    "Python embedding backend ready"
                );
                Some(EmbedBackend::Python(Mutex::new(client)))
            }
            Err(e) => {
                warn!("EmbedClient ping failed: {e}, continuing BM25-only");
                None
            }
        },
        Err(e) => {
            warn!("Failed to create EmbedClient: {e}, continuing BM25-only");
            None
        }
    }
}
