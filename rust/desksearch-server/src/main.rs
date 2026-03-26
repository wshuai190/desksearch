//! DeskSearch — Private semantic search engine for your files.
//!
//! Rust-powered backend with axum HTTP server.

mod config;
mod frontend;
mod routes;
mod state;
mod watcher;

use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;

use anyhow::Result;
use axum::Router;
use clap::{Parser, Subcommand};
use tower_http::cors::{Any, CorsLayer};
use tower_http::trace::TraceLayer;
use tracing::{info, warn};
use tracing_subscriber::EnvFilter;

use desksearch_indexer::{ChunkerConfig, FileWalker};
use desksearch_indexer::parsers;

use config::DeskSearchConfig;
use state::AppState;

#[derive(Parser)]
#[command(name = "desksearch", about = "Private semantic search for your files")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Start the DeskSearch server.
    Serve {
        /// Port to listen on.
        #[arg(short, long)]
        port: Option<u16>,
        /// Data directory for indexes and metadata.
        #[arg(short, long)]
        data_dir: Option<PathBuf>,
    },
    /// Index files in the specified directory.
    Index {
        /// Directory to index.
        path: PathBuf,
        /// Data directory for indexes and metadata.
        #[arg(short, long)]
        data_dir: Option<PathBuf>,
    },
    /// Show index status and statistics.
    Status {
        /// Data directory for indexes and metadata.
        #[arg(short, long)]
        data_dir: Option<PathBuf>,
    },
    /// Search the index from the command line.
    Search {
        /// Search query text.
        query: String,
        /// Number of results to return.
        #[arg(short = 'k', long, default_value = "10")]
        top_k: usize,
        /// Data directory for indexes and metadata.
        #[arg(short, long)]
        data_dir: Option<PathBuf>,
    },
    /// Show or edit configuration.
    Config {
        /// Set a config value (key=value).
        #[arg(long)]
        set: Option<String>,
    },
    /// Run indexing and search benchmarks.
    Benchmark {
        /// Directory to benchmark.
        path: Option<PathBuf>,
        /// Data directory for indexes and metadata.
        #[arg(short, long)]
        data_dir: Option<PathBuf>,
    },
}

fn default_data_dir() -> PathBuf {
    dirs_next::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".desksearch")
}

/// Detect project root by walking up from the executable or current dir.
fn detect_project_root() -> PathBuf {
    // Try the known project root first (compile-time)
    let compile_time_root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    if compile_time_root.join("scripts/embed_server.py").exists() {
        return std::fs::canonicalize(compile_time_root).unwrap_or_else(|_| PathBuf::from("."));
    }
    // Fallback: current directory
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();

    let cli = Cli::parse();

    // Load config
    let config = DeskSearchConfig::load();

    match cli.command {
        Commands::Serve { port, data_dir } => {
            let port = port.unwrap_or(config.port);
            let data_dir = data_dir.or(config.data_dir.clone()).unwrap_or_else(default_data_dir);
            serve(port, data_dir, &config).await?;
        }
        Commands::Index { path, data_dir } => {
            let data_dir = data_dir.or(config.data_dir.clone()).unwrap_or_else(default_data_dir);
            index_directory(&path, &data_dir, &config)?;
        }
        Commands::Status { data_dir } => {
            let data_dir = data_dir.or(config.data_dir.clone()).unwrap_or_else(default_data_dir);
            show_status(&data_dir)?;
        }
        Commands::Search { query, top_k, data_dir } => {
            let data_dir = data_dir.or(config.data_dir.clone()).unwrap_or_else(default_data_dir);
            cli_search(&query, top_k, &data_dir, &config)?;
        }
        Commands::Config { set } => {
            cli_config(set)?;
        }
        Commands::Benchmark { path, data_dir } => {
            let data_dir = data_dir.or(config.data_dir.clone()).unwrap_or_else(default_data_dir);
            cli_benchmark(path, &data_dir, &config)?;
        }
    }

    Ok(())
}

async fn serve(port: u16, data_dir: PathBuf, config: &DeskSearchConfig) -> Result<()> {
    info!("Starting DeskSearch server on port {port}");
    info!("Data directory: {}", data_dir.display());

    let project_root = detect_project_root();
    let state = Arc::new(AppState::new(&data_dir, &project_root, config)?);

    // Spawn file watcher if there are watched folders
    let watch_folders: Vec<String> = config
        .watched_folders
        .iter()
        .chain(config.folders.iter().map(|f| &f.path))
        .cloned()
        .collect();
    if !watch_folders.is_empty() {
        let _watcher_handle = watcher::spawn_watcher(state.clone(), watch_folders);
    }

    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    let app = Router::new()
        .nest("/api", routes::api_router(state.clone()))
        .merge(frontend::frontend_router())
        .layer(cors)
        .layer(TraceLayer::new_for_http());

    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    info!("DeskSearch ready at http://{addr}");

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}

fn index_directory(path: &PathBuf, data_dir: &PathBuf, config: &DeskSearchConfig) -> Result<()> {
    use desksearch_core::SearchConfig;
    use desksearch_indexer::MetadataStore;

    info!("Indexing directory: {}", path.display());

    let walker = FileWalker::new(vec![path.clone()]);
    let result = walker.walk()?;

    info!(
        "Found {} files ({} skipped) in {}ms",
        result.files.len(),
        result.skipped,
        result.elapsed_ms
    );

    // Open stores
    std::fs::create_dir_all(data_dir)?;
    let index_dir = data_dir.join("index");
    let db_path = data_dir.join("metadata.db");

    // Try to set up embedding
    let project_root = detect_project_root();
    let python_path = project_root.join(".venv/bin/python3");
    let script_path = project_root.join("scripts/embed_server.py");
    let vector_path = data_dir.join("vectors.usearch");

    let mut embed_client = if python_path.exists() && script_path.exists() {
        match desksearch_core::EmbedClient::new(
            python_path.to_str().unwrap_or("python3"),
            script_path.to_str().unwrap_or(""),
            config.embedding_dim,
            config.embedding_layers,
        ) {
            Ok(mut client) => {
                if client.ping().is_ok() {
                    info!("EmbedClient ready for CLI indexing");
                    Some(client)
                } else {
                    warn!("EmbedClient ping failed, BM25-only");
                    None
                }
            }
            Err(e) => {
                warn!("Failed to create EmbedClient: {e}, BM25-only");
                None
            }
        }
    } else {
        None
    };

    let engine = if embed_client.is_some() {
        match desksearch_core::VectorIndex::open_or_create(&vector_path, config.embedding_dim) {
            Ok(vi) => SearchEngine::new_hybrid(&index_dir, SearchConfig::default(), vi)?,
            Err(e) => {
                warn!("Failed to create VectorIndex: {e}, BM25-only");
                embed_client = None;
                SearchEngine::new(&index_dir, SearchConfig::default())?
            }
        }
    } else {
        SearchEngine::new(&index_dir, SearchConfig::default())?
    };

    let store = MetadataStore::open(&db_path)?;
    let chunker_config = ChunkerConfig::default();
    let mut writer = engine.bm25().writer(50)?;

    let mut indexed = 0usize;
    let mut skipped = result.skipped;

    // Batch embedding buffers
    let mut pending_embed_texts: Vec<String> = Vec::new();
    let mut pending_embed_ids: Vec<u64> = Vec::new();

    for file_path in &result.files {
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

        // Content hash for dedup
        let content_hash = {
            use std::hash::{Hash, Hasher};
            let mut hasher = std::collections::hash_map::DefaultHasher::new();
            text.as_bytes().hash(&mut hasher);
            format!("{:x}", hasher.finish())
        };

        // Skip if unchanged
        if !store.needs_reindex(&path_str, &content_hash)? {
            continue;
        }

        // Upsert file record
        let doc_id = store.upsert_file(
            &path_str,
            &file_name,
            &extension,
            size_bytes,
            &content_hash,
            modified_time,
        )?;

        // Replace chunks
        let _ = store.delete_chunks_for_doc(doc_id);
        engine.bm25().delete_by_path(&mut writer, &path_str);

        let chunks = desksearch_indexer::chunker::chunk_text(&text, &chunker_config);
        for chunk in &chunks {
            let chunk_id = store.insert_chunk(doc_id, chunk.index as i64, &chunk.text, chunk.offset as i64)?;
            engine.bm25().add_chunk(&mut writer, chunk_id as u64, &chunk.text, &path_str)?;

            if embed_client.is_some() {
                pending_embed_texts.push(chunk.text.clone());
                pending_embed_ids.push(chunk_id as u64);
            }
        }

        // Flush embedding batch
        if pending_embed_texts.len() >= 32 {
            if let Some(ref mut client) = embed_client {
                if let Ok(embeddings) = client.embed(&pending_embed_texts) {
                    for (cid, emb) in pending_embed_ids.iter().zip(embeddings.iter()) {
                        let _ = engine.add_vector(*cid, emb);
                    }
                }
            }
            pending_embed_texts.clear();
            pending_embed_ids.clear();
        }

        indexed += 1;
    }

    // Flush remaining embeddings
    if !pending_embed_texts.is_empty() {
        if let Some(ref mut client) = embed_client {
            if let Ok(embeddings) = client.embed(&pending_embed_texts) {
                for (cid, emb) in pending_embed_ids.iter().zip(embeddings.iter()) {
                    let _ = engine.add_vector(*cid, emb);
                }
            }
        }
    }

    writer.commit()?;

    if engine.has_dense() {
        let _ = engine.save_vectors();
    }

    info!("Indexed {indexed} files ({skipped} skipped)");
    println!("Indexed {indexed} files ({skipped} skipped)");
    println!("Total files: {}", store.file_count()?);
    println!("Total chunks: {}", store.chunk_count()?);

    Ok(())
}

fn show_status(data_dir: &PathBuf) -> Result<()> {
    let db_path = data_dir.join("metadata.db");
    if !db_path.exists() {
        println!("No DeskSearch index found at {}", data_dir.display());
        return Ok(());
    }

    let store = desksearch_indexer::MetadataStore::open(&db_path)?;
    println!("DeskSearch Index Status");
    println!("=======================");
    println!("Data directory: {}", data_dir.display());
    println!("Files indexed:  {}", store.file_count()?);
    println!("Total chunks:   {}", store.chunk_count()?);

    Ok(())
}

fn cli_search(query: &str, top_k: usize, data_dir: &PathBuf, config: &DeskSearchConfig) -> Result<()> {
    use desksearch_core::{SearchConfig, SearchQuery};

    let index_dir = data_dir.join("index");
    if !index_dir.exists() {
        println!("No index found at {}", data_dir.display());
        return Ok(());
    }

    let project_root = detect_project_root();
    let python_path = project_root.join(".venv/bin/python3");
    let script_path = project_root.join("scripts/embed_server.py");
    let vector_path = data_dir.join("vectors.usearch");

    // Try to create embed client for dense search
    let mut embed_client = if python_path.exists() && script_path.exists() {
        desksearch_core::EmbedClient::new(
            python_path.to_str().unwrap_or("python3"),
            script_path.to_str().unwrap_or(""),
            config.embedding_dim,
            config.embedding_layers,
        ).ok()
    } else {
        None
    };

    let engine = if embed_client.is_some() && vector_path.exists() {
        match desksearch_core::VectorIndex::open_or_create(&vector_path, config.embedding_dim) {
            Ok(vi) => SearchEngine::new_hybrid(&index_dir, SearchConfig::default(), vi)?,
            Err(_) => {
                embed_client = None;
                SearchEngine::new(&index_dir, SearchConfig::default())?
            }
        }
    } else {
        SearchEngine::new(&index_dir, SearchConfig::default())?
    };

    // Embed query if possible
    let query_embedding = embed_client
        .as_mut()
        .and_then(|c| c.embed_query(query).ok());

    let search_query = SearchQuery {
        text: query.to_string(),
        top_k: Some(top_k),
        file_type: None,
        folder: None,
    };

    let start = std::time::Instant::now();
    let results = engine.search(&search_query, query_embedding.as_deref())?;
    let elapsed = start.elapsed();

    println!("Search: \"{query}\" ({} results in {:.1}ms)", results.len(), elapsed.as_secs_f64() * 1000.0);
    println!("{}", "=".repeat(60));

    for (i, r) in results.iter().enumerate() {
        println!("\n{}. [score: {:.4}] {}", i + 1, r.score, r.file_path);
        let snippet = r.snippet.plain.replace('\n', " ");
        let snippet = if snippet.len() > 200 { &snippet[..200] } else { &snippet };
        println!("   {snippet}");
        if let (Some(bm25), Some(dense)) = (r.bm25_rank, r.dense_rank) {
            println!("   (BM25 rank: {bm25}, dense rank: {dense})");
        }
    }

    Ok(())
}

fn cli_config(set: Option<String>) -> Result<()> {
    let config_path = default_data_dir().join("config.json");

    if let Some(kv) = set {
        let mut config = DeskSearchConfig::load_from(&config_path);
        if let Some((key, value)) = kv.split_once('=') {
            let mut json = serde_json::to_value(&config)?;
            if let Some(obj) = json.as_object_mut() {
                // Try to parse as number, then bool, then string
                let parsed: serde_json::Value = if let Ok(n) = value.parse::<i64>() {
                    serde_json::Value::Number(n.into())
                } else if let Ok(b) = value.parse::<bool>() {
                    serde_json::Value::Bool(b)
                } else {
                    serde_json::Value::String(value.to_string())
                };
                obj.insert(key.to_string(), parsed);
            }
            config = serde_json::from_value(json)?;
            config.save_to(&config_path)?;
            println!("Set {key} = {value}");
        } else {
            println!("Invalid format. Use: --set key=value");
        }
    } else {
        let config = DeskSearchConfig::load_from(&config_path);
        let json = serde_json::to_string_pretty(&config)?;
        println!("Config ({}):\n{json}", config_path.display());
    }

    Ok(())
}

fn cli_benchmark(path: Option<PathBuf>, data_dir: &PathBuf, _config: &DeskSearchConfig) -> Result<()> {
    use desksearch_core::{SearchConfig, SearchQuery};
    use desksearch_indexer::MetadataStore;

    let path = path.unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
    println!("Benchmark: indexing {}", path.display());

    let bench_dir = data_dir.join("benchmark");
    std::fs::create_dir_all(&bench_dir)?;
    let index_dir = bench_dir.join("index");
    let db_path = bench_dir.join("metadata.db");

    // Walk
    let walk_start = std::time::Instant::now();
    let walker = FileWalker::new(vec![path.clone()]);
    let result = walker.walk()?;
    let walk_time = walk_start.elapsed();
    println!("Walk: {} files in {:.1}ms", result.files.len(), walk_time.as_secs_f64() * 1000.0);

    // Index
    let index_start = std::time::Instant::now();
    let engine = SearchEngine::new(&index_dir, SearchConfig::default())?;
    let store = MetadataStore::open(&db_path)?;
    let chunker_config = ChunkerConfig::default();
    let mut writer = engine.bm25().writer(50)?;

    let mut total_chunks = 0usize;
    for file_path in &result.files {
        let path_str = file_path.to_string_lossy();
        let text = match parsers::parse_file(file_path) {
            Ok(Some(text)) => text,
            _ => continue,
        };

        let file_name = file_path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
        let extension = file_path.extension().map(|e| e.to_string_lossy().to_string()).unwrap_or_default();
        let metadata = std::fs::metadata(file_path).ok();
        let size_bytes = metadata.as_ref().map(|m| m.len() as i64).unwrap_or(0);
        let modified_time = metadata
            .as_ref()
            .and_then(|m| m.modified().ok())
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_secs_f64())
            .unwrap_or(0.0);
        let content_hash = format!("{:x}", {
            use std::hash::{Hash, Hasher};
            let mut h = std::collections::hash_map::DefaultHasher::new();
            text.as_bytes().hash(&mut h);
            h.finish()
        });

        let doc_id = store.upsert_file(&path_str, &file_name, &extension, size_bytes, &content_hash, modified_time)?;
        let chunks = desksearch_indexer::chunker::chunk_text(&text, &chunker_config);
        for chunk in &chunks {
            let chunk_id = store.insert_chunk(doc_id, chunk.index as i64, &chunk.text, chunk.offset as i64)?;
            engine.bm25().add_chunk(&mut writer, chunk_id as u64, &chunk.text, &path_str)?;
            total_chunks += 1;
        }
    }
    writer.commit()?;
    engine.bm25().reader.reload()?;
    let index_time = index_start.elapsed();
    println!("Index: {total_chunks} chunks in {:.1}ms", index_time.as_secs_f64() * 1000.0);

    // Search benchmark
    let queries = ["search", "file", "data", "error", "config"];
    println!("\nSearch benchmarks:");
    for q in &queries {
        let search_query = SearchQuery {
            text: q.to_string(),
            top_k: Some(10),
            file_type: None,
            folder: None,
        };
        let start = std::time::Instant::now();
        let results = engine.search(&search_query, None)?;
        let elapsed = start.elapsed();
        println!("  \"{q}\": {} results in {:.2}ms", results.len(), elapsed.as_secs_f64() * 1000.0);
    }

    // Cleanup benchmark data
    let _ = std::fs::remove_dir_all(&bench_dir);

    Ok(())
}

use desksearch_core::SearchEngine;
