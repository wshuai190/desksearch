#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Building React UI..."
(cd src/ui && npm ci && npm run build)

echo "==> Installing Electron dependencies..."
(cd electron && npm ci)

echo "==> Packaging desktop app with electron-builder..."
(cd electron && npx electron-builder)

echo ""
echo "==> Done! Artifacts are in dist/electron/"
ls -lh dist/electron/ 2>/dev/null || true
