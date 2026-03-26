use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use tracing::{debug, info};
use usearch::Index;

/// ANN vector index backed by usearch.
pub struct VectorIndex {
    index: Index,
    dimension: usize,
    index_path: PathBuf,
}

impl VectorIndex {
    /// Open or create a vector index at the given path.
    pub fn open_or_create(path: &Path, dimension: usize) -> Result<Self> {
        let opts = usearch::IndexOptions {
            dimensions: dimension,
            metric: usearch::MetricKind::IP,
            quantization: usearch::ScalarKind::F32,
            connectivity: 16,
            expansion_add: 128,
            expansion_search: 64,
            multi: false,
        };

        let index = Index::new(&opts).context("failed to create usearch index")?;

        let index_path = path.to_path_buf();
        if index_path.exists() {
            info!(path = %index_path.display(), "loading existing vector index");
            index
                .load(index_path.to_str().unwrap_or_default())
                .context("failed to load vector index from disk")?;
            debug!(len = index.size(), "loaded vector index");
        } else {
            info!(path = %index_path.display(), dimension, "creating new vector index");
            // Reserve initial capacity; usearch will grow as needed.
            index
                .reserve(1024)
                .context("failed to reserve index capacity")?;
        }

        Ok(Self {
            index,
            dimension,
            index_path,
        })
    }

    /// Add a vector for a chunk. `key` = chunk_id.
    pub fn add(&self, key: u64, vector: &[f32]) -> Result<()> {
        assert_eq!(
            vector.len(),
            self.dimension,
            "vector length {} != dimension {}",
            vector.len(),
            self.dimension
        );
        self.index
            .add(key, vector)
            .context("failed to add vector to index")?;
        Ok(())
    }

    /// Remove a vector by key.
    pub fn remove(&self, key: u64) -> Result<()> {
        self.index
            .remove(key)
            .context("failed to remove vector from index")?;
        Ok(())
    }

    /// Search for nearest neighbors. Returns `(key, distance)` pairs.
    pub fn search(&self, query: &[f32], top_k: usize) -> Result<Vec<(u64, f32)>> {
        assert_eq!(
            query.len(),
            self.dimension,
            "query vector length {} != dimension {}",
            query.len(),
            self.dimension
        );

        let results = self
            .index
            .search(query, top_k)
            .context("usearch search failed")?;

        Ok(results
            .keys
            .into_iter()
            .zip(results.distances.into_iter())
            .collect())
    }

    /// Save index to disk.
    pub fn save(&self) -> Result<()> {
        // Ensure parent directory exists.
        if let Some(parent) = self.index_path.parent() {
            std::fs::create_dir_all(parent).context("failed to create index directory")?;
        }
        self.index
            .save(self.index_path.to_str().unwrap_or_default())
            .context("failed to save vector index")?;
        info!(path = %self.index_path.display(), len = self.index.size(), "saved vector index");
        Ok(())
    }

    /// Number of vectors in the index.
    pub fn len(&self) -> usize {
        self.index.size()
    }

    /// Whether the index is empty.
    pub fn is_empty(&self) -> bool {
        self.index.size() == 0
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn dummy_vector(dim: usize, val: f32) -> Vec<f32> {
        let mut v = vec![val; dim];
        // L2 normalize
        let norm: f32 = v.iter().map(|x| x * x).sum::<f32>().sqrt();
        if norm > 0.0 {
            v.iter_mut().for_each(|x| *x /= norm);
        }
        v
    }

    #[test]
    fn test_create_and_add() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.usearch");
        let idx = VectorIndex::open_or_create(&path, 64).unwrap();

        assert_eq!(idx.len(), 0);
        assert!(idx.is_empty());

        idx.add(1, &dummy_vector(64, 1.0)).unwrap();
        idx.add(2, &dummy_vector(64, 0.5)).unwrap();

        assert_eq!(idx.len(), 2);
        assert!(!idx.is_empty());
    }

    #[test]
    fn test_search() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.usearch");
        let idx = VectorIndex::open_or_create(&path, 4).unwrap();

        // Add a few vectors with distinct directions.
        let v1 = vec![1.0, 0.0, 0.0, 0.0];
        let v2 = vec![0.0, 1.0, 0.0, 0.0];
        let v3 = vec![0.7071, 0.7071, 0.0, 0.0];

        idx.add(10, &v1).unwrap();
        idx.add(20, &v2).unwrap();
        idx.add(30, &v3).unwrap();

        // Query close to v1
        let query = vec![0.9, 0.1, 0.0, 0.0];
        let results = idx.search(&query, 2).unwrap();

        assert_eq!(results.len(), 2);
        // First result should be key 10 (v1) or 30 (v3), both close to query.
        let keys: Vec<u64> = results.iter().map(|(k, _)| *k).collect();
        assert!(keys.contains(&10) || keys.contains(&30));
    }

    #[test]
    fn test_save_and_reload() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("persist.usearch");

        // Create and populate.
        {
            let idx = VectorIndex::open_or_create(&path, 4).unwrap();
            idx.add(1, &[1.0, 0.0, 0.0, 0.0]).unwrap();
            idx.add(2, &[0.0, 1.0, 0.0, 0.0]).unwrap();
            idx.save().unwrap();
            assert_eq!(idx.len(), 2);
        }

        // Reload and verify.
        {
            let idx = VectorIndex::open_or_create(&path, 4).unwrap();
            assert_eq!(idx.len(), 2);

            let results = idx.search(&[1.0, 0.0, 0.0, 0.0], 1).unwrap();
            assert_eq!(results.len(), 1);
            assert_eq!(results[0].0, 1);
        }
    }

    #[test]
    fn test_remove() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.usearch");
        let idx = VectorIndex::open_or_create(&path, 4).unwrap();

        idx.add(1, &[1.0, 0.0, 0.0, 0.0]).unwrap();
        idx.add(2, &[0.0, 1.0, 0.0, 0.0]).unwrap();
        assert_eq!(idx.len(), 2);

        idx.remove(1).unwrap();
        // Note: usearch may not decrement size on remove (lazy deletion),
        // but the vector should no longer appear in search results.
        let results = idx.search(&[1.0, 0.0, 0.0, 0.0], 2).unwrap();
        // After removal, key 1 should not be the top result.
        if !results.is_empty() {
            // Key 2 should rank higher since key 1 is removed.
            assert_eq!(results[0].0, 2);
        }
    }

    #[test]
    fn test_empty_search() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("empty.usearch");
        let idx = VectorIndex::open_or_create(&path, 4).unwrap();

        let results = idx.search(&[1.0, 0.0, 0.0, 0.0], 5).unwrap();
        assert!(results.is_empty());
    }

    #[test]
    #[should_panic(expected = "vector length")]
    fn test_dimension_mismatch_on_add() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.usearch");
        let idx = VectorIndex::open_or_create(&path, 4).unwrap();
        idx.add(1, &[1.0, 0.0]).unwrap(); // wrong dimension
    }

    #[test]
    #[should_panic(expected = "query vector length")]
    fn test_dimension_mismatch_on_search() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.usearch");
        let idx = VectorIndex::open_or_create(&path, 4).unwrap();
        idx.add(1, &[1.0, 0.0, 0.0, 0.0]).unwrap();
        idx.search(&[1.0, 0.0], 1).unwrap(); // wrong dimension
    }
}
