#!/usr/bin/env python3
"""Export Starbucks model to ONNX for 3 tiers (fast/middle/pro).

Each tier uses a different number of transformer layers and output dimensions:
  - fast:   2 layers, 32d
  - middle: 4 layers, 64d
  - pro:    6 layers, 128d

The full 6-layer model is loaded once from ~/.desksearch/models/starbucks-6layer,
then subsets of layers are used for each tier via config modification.
"""

import os
import json
import shutil
from pathlib import Path

import torch
import torch.nn as nn
from transformers import AutoModel, AutoConfig, AutoTokenizer

MODEL_DIR = Path.home() / ".desksearch" / "models"
SOURCE_MODEL = MODEL_DIR / "starbucks-6layer"

TIERS = [
    {"name": "fast",    "layers": 2, "dim": 32,  "output": "starbucks-fast.onnx"},
    {"name": "middle",  "layers": 4, "dim": 64,  "output": "starbucks-middle.onnx"},
    {"name": "pro",     "layers": 6, "dim": 128, "output": "starbucks-pro.onnx"},
]


class StarbucksTierModel(nn.Module):
    """Wraps a BERT model to output only the first `dim` dimensions of the last hidden state."""

    def __init__(self, bert_model, dim):
        super().__init__()
        self.bert = bert_model
        self.dim = dim

    def forward(self, input_ids, attention_mask):
        outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        # Slice to the target dimensionality (Matryoshka-style)
        return outputs.last_hidden_state[:, :, :self.dim]


def export_tier(tier, tokenizer):
    name = tier["name"]
    num_layers = tier["layers"]
    dim = tier["dim"]
    output_path = MODEL_DIR / tier["output"]

    print(f"\n{'='*60}")
    print(f"Exporting {name} tier: {num_layers} layers, {dim}d → {output_path}")
    print(f"{'='*60}")

    # Load config with reduced layers
    config = AutoConfig.from_pretrained(str(SOURCE_MODEL))
    config.num_hidden_layers = num_layers

    # Load model with subset of layers
    model = AutoModel.from_pretrained(str(SOURCE_MODEL), config=config)
    model.eval()

    # Wrap to slice output dimensions
    wrapped = StarbucksTierModel(model, dim)
    wrapped.eval()

    # Create dummy input
    dummy_input_ids = torch.ones(1, 32, dtype=torch.long)
    dummy_attention_mask = torch.ones(1, 32, dtype=torch.long)

    # Export to ONNX (legacy exporter for self-contained files)
    torch.onnx.export(
        wrapped,
        (dummy_input_ids, dummy_attention_mask),
        str(output_path),
        input_names=["input_ids", "attention_mask"],
        output_names=["last_hidden_state"],
        dynamic_axes={
            "input_ids": {0: "batch_size", 1: "sequence_length"},
            "attention_mask": {0: "batch_size", 1: "sequence_length"},
            "last_hidden_state": {0: "batch_size", 1: "sequence_length"},
        },
        opset_version=14,
        do_constant_folding=True,
        dynamo=False,
    )

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"✓ Exported {name}: {size_mb:.2f} MB")
    return size_mb


def save_tokenizer():
    """Save tokenizer files to the models directory."""
    tokenizer = AutoTokenizer.from_pretrained(str(SOURCE_MODEL))
    tokenizer.save_pretrained(str(MODEL_DIR))
    print(f"\n✓ Tokenizer saved to {MODEL_DIR}")
    return tokenizer


def main():
    print(f"Source model: {SOURCE_MODEL}")
    print(f"Output dir:   {MODEL_DIR}")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Save tokenizer first
    tokenizer = save_tokenizer()

    # Export each tier
    sizes = {}
    for tier in TIERS:
        sizes[tier["name"]] = export_tier(tier, tokenizer)

    # Summary
    print(f"\n{'='*60}")
    print("Export Summary:")
    print(f"{'='*60}")
    for tier in TIERS:
        print(f"  {tier['name']:>8}: {tier['layers']} layers, {tier['dim']:>3}d → {sizes[tier['name']]:.2f} MB")
    print(f"\nTokenizer: {MODEL_DIR / 'tokenizer.json'}")


if __name__ == "__main__":
    main()
