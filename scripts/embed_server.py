#!/usr/bin/env python3
"""Embedding subprocess worker for Rust binary.

Communicates via JSON-lines over stdin/stdout.
All logging goes to stderr; stdout is reserved for protocol messages.

Protocol:
  IN:  {"id": 1, "texts": ["chunk1", ...], "dim": 64, "layers": 4}
  OUT: {"id": 1, "embeddings": [[0.1, ...], ...], "dim": 64}
  ERR: {"id": 1, "error": "message"}
  CMD: {"id": 0, "cmd": "ping"}  -> {"id": 0, "status": "ok", "dim": 64, "backend": "starbucks"}
  CMD: {"id": 0, "cmd": "shutdown"} -> exit
"""

import json
import os
import sys
from pathlib import Path

BATCH_SIZE = 64
DEFAULT_DIM = 64
DEFAULT_LAYERS = 4
LOCAL_MODEL_DIR = Path.home() / ".desksearch" / "models" / "starbucks-6layer"
HF_MODEL_NAME = "ielabgroup/Starbucks-msmarco"
MAX_LAYERS = 6


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def activate_venv() -> None:
    """Activate .venv from script's parent directory if not already in a venv."""
    if os.environ.get("VIRTUAL_ENV"):
        return
    venv_dir = Path(__file__).resolve().parent.parent / ".venv"
    if not venv_dir.exists():
        return
    # Prepend venv bin to PATH and set VIRTUAL_ENV
    bin_dir = venv_dir / "bin"
    os.environ["VIRTUAL_ENV"] = str(venv_dir)
    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
    # Update site-packages
    import site
    site_packages = next(venv_dir.glob("lib/python*/site-packages"), None)
    if site_packages and str(site_packages) not in sys.path:
        sys.path.insert(0, str(site_packages))


def load_model(layers: int = DEFAULT_LAYERS):
    """Load the Starbucks model, returning (model, tokenizer)."""
    import torch  # noqa: F401
    from transformers import AutoConfig, AutoModel, AutoTokenizer

    if (LOCAL_MODEL_DIR / "config.json").exists():
        log(f"Loading local model from {LOCAL_MODEL_DIR} ({layers} layers)")
        model_path = LOCAL_MODEL_DIR
    else:
        log(f"Local model not found, downloading {HF_MODEL_NAME} ({layers} layers)")
        model_path = HF_MODEL_NAME

    config = AutoConfig.from_pretrained(model_path, num_hidden_layers=layers)

    # Suppress transformer weight mismatch warnings when loading fewer layers
    import logging
    tf_logger = logging.getLogger("transformers.modeling_utils")
    prev_level = tf_logger.level
    tf_logger.setLevel(logging.ERROR)
    model = AutoModel.from_pretrained(model_path, config=config).eval()
    tf_logger.setLevel(prev_level)

    for param in model.parameters():
        param.requires_grad = False

    tokenizer = AutoTokenizer.from_pretrained(model_path)
    return model, tokenizer


def embed_texts(model, tokenizer, texts: list, dim: int) -> list:
    """Embed texts using CLS token pooling, truncate to dim, L2 normalize."""
    import numpy as np
    import torch

    if not texts:
        return []

    all_embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        inputs = tokenizer(
            batch,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=256,
        )
        with torch.no_grad():
            outputs = model(**inputs, return_dict=True)

        # CLS token embedding, truncated to target dim
        cls = outputs.last_hidden_state[:, 0, :dim].cpu().numpy().astype(np.float32)
        all_embeddings.append(cls)

    embeddings = np.vstack(all_embeddings)

    # L2 normalize
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.clip(norms, 1e-9, None)
    embeddings = embeddings / norms

    return embeddings.tolist()


def write_response(obj: dict) -> None:
    """Write a JSON line to stdout and flush."""
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main() -> None:
    activate_venv()

    model, tokenizer = load_model(DEFAULT_LAYERS)
    current_layers = DEFAULT_LAYERS

    log(f"embed_server ready (backend=starbucks, dim={DEFAULT_DIM})")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            write_response({"id": None, "error": f"Invalid JSON: {e}"})
            continue

        req_id = req.get("id")

        try:
            # Handle special commands
            cmd = req.get("cmd")
            if cmd == "ping":
                write_response({
                    "id": req_id,
                    "status": "ok",
                    "dim": DEFAULT_DIM,
                    "backend": "starbucks",
                })
                continue
            elif cmd == "shutdown":
                log("embed_server shutting down")
                break

            # Embedding request
            texts = req.get("texts", [])
            dim = req.get("dim", DEFAULT_DIM)
            layers = req.get("layers", DEFAULT_LAYERS)

            if not isinstance(texts, list):
                write_response({"id": req_id, "error": "texts must be a list"})
                continue

            # Reload model if layer count changed
            if layers != current_layers:
                log(f"Reloading model with {layers} layers (was {current_layers})")
                model, tokenizer = load_model(layers)
                current_layers = layers

            embeddings = embed_texts(model, tokenizer, texts, dim)
            write_response({
                "id": req_id,
                "embeddings": embeddings,
                "dim": dim,
            })

        except Exception as e:
            write_response({"id": req_id, "error": str(e)})


if __name__ == "__main__":
    main()
