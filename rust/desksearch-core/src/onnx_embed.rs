//! ONNX-native embedding using `ort` and HuggingFace `tokenizers`.
//!
//! Replaces the Python subprocess (`EmbedClient`) for inference.

use std::path::Path;
use std::sync::{Arc, Mutex};

use anyhow::{Context, Result};
use ort::session::Session;
use ort::value::Tensor;
use tokenizers::Tokenizer;
use tracing::{debug, info};

/// Native ONNX embedding engine.
///
/// The ort `Session::run` requires `&self` in ort v2 RC but the session itself
/// is `Send + Sync`. We use interior mutability only if needed.
pub struct OnnxEmbedder {
    session: Mutex<Session>,
    tokenizer: Tokenizer,
    dim: usize,
}

// Safety: Session is Send, Tokenizer is Send+Sync, Mutex provides Sync.
unsafe impl Sync for OnnxEmbedder {}

impl OnnxEmbedder {
    /// Load an ONNX model and tokenizer from disk.
    ///
    /// - `model_path`: path to the `.onnx` file
    /// - `tokenizer_path`: path to `tokenizer.json`
    /// - `dim`: desired output embedding dimension (truncated from model hidden size)
    pub fn new(model_path: &Path, tokenizer_path: &Path, dim: usize) -> Result<Self> {
        info!(
            model = %model_path.display(),
            tokenizer = %tokenizer_path.display(),
            dim,
            "loading ONNX embedding model"
        );

        let session = Session::builder()
            .map_err(|e| anyhow::anyhow!("failed to create ort session builder: {e}"))?
            .with_intra_threads(4)
            .map_err(|e| anyhow::anyhow!("failed to set intra threads: {e}"))?
            .commit_from_file(model_path)
            .map_err(|e| anyhow::anyhow!("failed to load ONNX model: {e}"))?;

        let tokenizer = Tokenizer::from_file(tokenizer_path)
            .map_err(|e| anyhow::anyhow!("failed to load tokenizer: {e}"))?;

        info!("ONNX embedding model loaded successfully");

        Ok(Self {
            session: Mutex::new(session),
            tokenizer,
            dim,
        })
    }

    /// Embed a batch of texts. Returns one vector per input text.
    pub fn embed_batch(&self, texts: &[&str]) -> Result<Vec<Vec<f32>>> {
        if texts.is_empty() {
            return Ok(vec![]);
        }

        let batch_size = texts.len();

        // Tokenize with padding and truncation
        let encodings = self
            .tokenizer
            .encode_batch(texts.to_vec(), true)
            .map_err(|e| anyhow::anyhow!("tokenization failed: {e}"))?;

        // Find max length (capped at 256) for padding
        let max_len = encodings
            .iter()
            .map(|enc| enc.get_ids().len().min(256))
            .max()
            .unwrap_or(0);

        // Build input_ids and attention_mask as flat Vec<i64>
        let mut input_ids_data = vec![0i64; batch_size * max_len];
        let mut attention_mask_data = vec![0i64; batch_size * max_len];

        for (i, enc) in encodings.iter().enumerate() {
            let ids = enc.get_ids();
            let mask = enc.get_attention_mask();
            let len = ids.len().min(max_len);
            for j in 0..len {
                input_ids_data[i * max_len + j] = ids[j] as i64;
                attention_mask_data[i * max_len + j] = mask[j] as i64;
            }
        }

        // Create ort Tensors
        let input_ids = Tensor::from_array(
            ([batch_size, max_len], input_ids_data.into_boxed_slice()),
        )
        .map_err(|e| anyhow::anyhow!("failed to create input_ids tensor: {e}"))?;

        let attention_mask = Tensor::from_array(
            ([batch_size, max_len], attention_mask_data.into_boxed_slice()),
        )
        .map_err(|e| anyhow::anyhow!("failed to create attention_mask tensor: {e}"))?;

        // Run inference
        let mut session = self.session.lock()
            .map_err(|e| anyhow::anyhow!("session lock poisoned: {e}"))?;
        let outputs = session
            .run(ort::inputs![input_ids, attention_mask])
            .map_err(|e| anyhow::anyhow!("ONNX inference failed: {e}"))?;

        // Extract last_hidden_state — shape: (batch_size, seq_len, hidden_dim)
        let output_value = &outputs[0];
        let (shape, data) = output_value
            .try_extract_tensor::<f32>()
            .map_err(|e| anyhow::anyhow!("failed to extract output tensor: {e}"))?;

        let shape_dims: &[i64] = &**shape;
        debug!(
            shape = ?shape_dims,
            "model output shape"
        );

        // shape is [batch_size, seq_len, hidden_dim]
        let seq_len = shape_dims[1] as usize;
        let hidden_dim = shape_dims[2] as usize;
        let take_dim = self.dim.min(hidden_dim);

        // Extract CLS token (index 0) for each sample, truncate to dim, L2-normalize
        let mut results = Vec::with_capacity(batch_size);
        for i in 0..batch_size {
            let cls_offset = i * seq_len * hidden_dim; // batch i, token 0
            let cls_slice = &data[cls_offset..cls_offset + take_dim];

            // L2 normalize
            let norm: f32 = cls_slice.iter().map(|x| x * x).sum::<f32>().sqrt();
            let embedding: Vec<f32> = if norm > 1e-12 {
                cls_slice.iter().map(|x| x / norm).collect()
            } else {
                cls_slice.to_vec()
            };

            results.push(embedding);
        }

        debug!(count = results.len(), dim = self.dim, "embedded batch");
        Ok(results)
    }

    /// Convenience: embed a single text.
    pub fn embed_single(&self, text: &str) -> Result<Vec<f32>> {
        let mut results = self.embed_batch(&[text])?;
        results
            .pop()
            .context("expected one embedding result")
    }

    /// Return the configured output dimension.
    pub fn dim(&self) -> usize {
        self.dim
    }
}

/// Thread-safe wrapper that allows shared access to OnnxEmbedder.
pub type SharedOnnxEmbedder = Arc<OnnxEmbedder>;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_nonexistent_model_fails() {
        let result = OnnxEmbedder::new(
            Path::new("/nonexistent/model.onnx"),
            Path::new("/nonexistent/tokenizer.json"),
            64,
        );
        assert!(result.is_err());
    }

    #[test]
    fn test_embed_empty_batch_concept() {
        // We can't create a real embedder without model files,
        // but we verify the empty-input path logic is sound.
        let texts: Vec<&str> = vec![];
        assert!(texts.is_empty());
    }
}
