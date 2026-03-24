#!/usr/bin/env bash
# Build DeskSearch for distribution.
# Usage: ./scripts/build.sh [pypi|electron|all]
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

build_ui() {
    echo "=== Building UI ==="
    (cd src/ui && npm ci && npm run build)
    rm -rf src/desksearch/ui_dist
    cp -r src/ui/dist src/desksearch/ui_dist
    echo "✓ UI built"
}

build_pypi() {
    echo "=== Building PyPI package ==="
    source .venv/bin/activate
    build_ui
    python -m build --wheel --sdist
    echo "✓ PyPI package built in dist/"
}

build_backend_binary() {
    echo "=== Building standalone backend binary ==="
    source .venv/bin/activate
    pip install pyinstaller 2>/dev/null
    pyinstaller desksearch.spec --clean
    echo "✓ Backend binary at dist/desksearch-backend/"
}

build_electron() {
    echo "=== Building Electron app ==="
    build_backend_binary
    (cd electron && npm ci && npm run dist)
    echo "✓ Electron app at dist/electron/"
}

run_tests() {
    echo "=== Running tests ==="
    source .venv/bin/activate
    python -m pytest tests/ --tb=short -q
    echo "✓ Tests passed"
}

case "${1:-pypi}" in
    pypi)
        run_tests
        build_pypi
        ;;
    electron)
        run_tests
        build_electron
        ;;
    all)
        run_tests
        build_pypi
        build_electron
        ;;
    ui)
        build_ui
        ;;
    test)
        run_tests
        ;;
    *)
        echo "Usage: $0 [pypi|electron|all|ui|test]"
        exit 1
        ;;
esac

echo "=== Done ==="
