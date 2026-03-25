pub mod chunker;
pub mod parsers;
pub mod store;
pub mod walker;

// Re-export main types
pub use chunker::{Chunk, ChunkerConfig};
pub use store::MetadataStore;
pub use walker::FileWalker;
