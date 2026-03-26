pub mod bm25;
pub mod embed;
pub mod fusion;
pub mod search;
pub mod snippets;
pub mod vector;

// Re-export main types
pub use search::{SearchEngine, SearchResult, SearchQuery, SearchConfig};
pub use fusion::FusedResult;
pub use snippets::Snippet;
pub use embed::EmbedClient;
pub use vector::VectorIndex;
