use std::io::{BufRead, BufReader, BufWriter, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::time::{Duration, Instant};

use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use tracing::{debug, error, info, warn};

const READ_TIMEOUT: Duration = Duration::from_secs(30);

#[derive(Serialize)]
struct EmbedRequest {
    id: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    cmd: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    texts: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    dim: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    layers: Option<usize>,
}

#[derive(Deserialize, Debug)]
struct EmbedResponse {
    id: u64,
    #[serde(default)]
    embeddings: Option<Vec<Vec<f32>>>,
    #[serde(default)]
    status: Option<String>,
    #[serde(default)]
    error: Option<String>,
    #[serde(default)]
    #[allow(dead_code)]
    dim: Option<usize>,
}

/// Client that communicates with the Python embedding subprocess via JSON-lines.
pub struct EmbedClient {
    child: Child,
    stdin: BufWriter<ChildStdin>,
    stdout: BufReader<ChildStdout>,
    dimension: usize,
    layers: usize,
    next_id: u64,
}

impl EmbedClient {
    /// Spawn the Python embedding subprocess.
    ///
    /// - `python_path`: path to python3 binary (e.g., from venv)
    /// - `script_path`: path to `scripts/embed_server.py`
    /// - `dim`: embedding dimension (32, 64, or 128)
    /// - `layers`: model layers (2, 4, or 6)
    pub fn new(python_path: &str, script_path: &str, dim: usize, layers: usize) -> Result<Self> {
        info!(
            python = python_path,
            script = script_path,
            dim,
            layers,
            "spawning embedding subprocess"
        );

        let mut child = Command::new(python_path)
            .arg(script_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .context("failed to spawn embed_server.py")?;

        let stdin = child
            .stdin
            .take()
            .context("failed to capture child stdin")?;
        let stdout = child
            .stdout
            .take()
            .context("failed to capture child stdout")?;

        let mut client = Self {
            child,
            stdin: BufWriter::new(stdin),
            stdout: BufReader::new(stdout),
            dimension: dim,
            layers,
            next_id: 1,
        };

        // Verify the subprocess is alive with a ping.
        client.ping().context("initial ping to embed subprocess failed")?;
        info!("embedding subprocess ready");

        Ok(client)
    }

    /// Send a ping to verify the subprocess is alive.
    pub fn ping(&mut self) -> Result<()> {
        let req = EmbedRequest {
            id: 0,
            cmd: Some("ping".into()),
            texts: None,
            dim: None,
            layers: None,
        };
        self.send_request(&req)?;
        let resp = self.read_response()?;
        if resp.status.as_deref() != Some("ok") {
            bail!(
                "ping failed: unexpected response: {:?}",
                resp.status
            );
        }
        debug!("ping ok");
        Ok(())
    }

    /// Embed a batch of texts. Returns `Vec<Vec<f32>>` of embeddings.
    pub fn embed(&mut self, texts: &[String]) -> Result<Vec<Vec<f32>>> {
        if texts.is_empty() {
            return Ok(vec![]);
        }

        let id = self.next_id;
        self.next_id += 1;

        let req = EmbedRequest {
            id,
            cmd: None,
            texts: Some(texts.to_vec()),
            dim: Some(self.dimension),
            layers: Some(self.layers),
        };
        self.send_request(&req)?;
        let resp = self.read_response()?;

        if let Some(err) = resp.error {
            bail!("embed error from subprocess: {err}");
        }
        if resp.id != id {
            bail!("response id mismatch: expected {id}, got {}", resp.id);
        }

        let embeddings = resp
            .embeddings
            .context("missing embeddings in response")?;

        if embeddings.len() != texts.len() {
            bail!(
                "embedding count mismatch: sent {} texts, got {} embeddings",
                texts.len(),
                embeddings.len()
            );
        }

        debug!(count = embeddings.len(), "embedded batch");
        Ok(embeddings)
    }

    /// Embed a single query string.
    pub fn embed_query(&mut self, query: &str) -> Result<Vec<f32>> {
        let results = self.embed(&[query.to_string()])?;
        results
            .into_iter()
            .next()
            .context("expected one embedding for query")
    }

    /// Gracefully shut down the subprocess.
    pub fn shutdown(&mut self) -> Result<()> {
        info!("shutting down embedding subprocess");
        let req = EmbedRequest {
            id: 0,
            cmd: Some("shutdown".into()),
            texts: None,
            dim: None,
            layers: None,
        };
        // Best-effort: send shutdown and ignore write errors (process may already be gone).
        if let Err(e) = self.send_request(&req) {
            warn!("failed to send shutdown command: {e}");
        }
        let _ = self.child.wait();
        Ok(())
    }

    fn send_request(&mut self, req: &EmbedRequest) -> Result<()> {
        let json = serde_json::to_string(req).context("failed to serialize request")?;
        debug!(json = %json, "sending request");
        writeln!(self.stdin, "{json}").context("failed to write to subprocess stdin")?;
        self.stdin.flush().context("failed to flush stdin")?;
        Ok(())
    }

    fn read_response(&mut self) -> Result<EmbedResponse> {
        let start = Instant::now();
        let mut line = String::new();

        // Poll in a loop with a timeout.
        loop {
            if start.elapsed() > READ_TIMEOUT {
                error!("embed subprocess read timeout after {READ_TIMEOUT:?}");
                let _ = self.child.kill();
                bail!("embed subprocess timed out after {READ_TIMEOUT:?}");
            }

            line.clear();
            let n = self
                .stdout
                .read_line(&mut line)
                .context("failed to read from subprocess stdout")?;

            if n == 0 {
                bail!("embed subprocess closed stdout unexpectedly");
            }

            let trimmed = line.trim();
            if trimmed.is_empty() {
                continue;
            }

            let resp: EmbedResponse =
                serde_json::from_str(trimmed).context("failed to parse subprocess response")?;
            return Ok(resp);
        }
    }
}

impl Drop for EmbedClient {
    fn drop(&mut self) {
        if let Err(e) = self.shutdown() {
            warn!("error during EmbedClient drop: {e}");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_embed_request_serialization() {
        let req = EmbedRequest {
            id: 1,
            cmd: None,
            texts: Some(vec!["hello world".into()]),
            dim: Some(64),
            layers: Some(4),
        };
        let json = serde_json::to_string(&req).unwrap();
        assert!(json.contains("\"id\":1"));
        assert!(json.contains("\"texts\""));
        assert!(json.contains("\"dim\":64"));
        assert!(json.contains("\"layers\":4"));
        // cmd should be omitted
        assert!(!json.contains("\"cmd\""));
    }

    #[test]
    fn test_ping_request_serialization() {
        let req = EmbedRequest {
            id: 0,
            cmd: Some("ping".into()),
            texts: None,
            dim: None,
            layers: None,
        };
        let json = serde_json::to_string(&req).unwrap();
        assert!(json.contains("\"cmd\":\"ping\""));
        assert!(!json.contains("\"texts\""));
    }

    #[test]
    fn test_embed_response_deserialization() {
        let json = r#"{"id": 1, "embeddings": [[0.1, 0.2], [0.3, 0.4]], "dim": 2}"#;
        let resp: EmbedResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.id, 1);
        assert_eq!(resp.dim, Some(2));
        let embs = resp.embeddings.unwrap();
        assert_eq!(embs.len(), 2);
        assert_eq!(embs[0], vec![0.1, 0.2]);
    }

    #[test]
    fn test_ping_response_deserialization() {
        let json = r#"{"id": 0, "status": "ok", "dim": 64, "backend": "starbucks"}"#;
        let resp: EmbedResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.id, 0);
        assert_eq!(resp.status.as_deref(), Some("ok"));
    }

    #[test]
    fn test_error_response_deserialization() {
        let json = r#"{"id": 1, "error": "model not loaded"}"#;
        let resp: EmbedResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.id, 1);
        assert_eq!(resp.error.as_deref(), Some("model not loaded"));
        assert!(resp.embeddings.is_none());
    }

    #[test]
    fn test_spawn_nonexistent_python_fails() {
        let result = EmbedClient::new(
            "/nonexistent/python3",
            "/nonexistent/embed_server.py",
            64,
            4,
        );
        assert!(result.is_err());
    }
}
