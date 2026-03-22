# Contributing to DeskSearch

Thanks for your interest in contributing! This guide will help you get started.

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/desksearch.git
   cd desksearch
   ```
3. **Install** development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```
4. **Create a branch** for your change:
   ```bash
   git checkout -b feature/my-feature
   ```

## Development Setup

### Backend (Python)

```bash
# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run a specific test
pytest tests/test_search.py -v
```

### Frontend (Web UI)

```bash
cd src/ui
npm install
npm run dev    # Start dev server with hot reload
npm run build  # Production build
```

## Making Changes

### Code Style

- **Python**: Follow PEP 8. Use type hints where practical.
- **TypeScript/React**: Follow the existing patterns in `src/ui/`.
- Keep changes focused — one feature or fix per PR.

### Testing

- Add tests for new functionality
- Ensure all existing tests pass: `pytest`
- Test across file formats if touching parsing/indexing

### Commit Messages

Use clear, descriptive commit messages:

```
feat: add EPUB parser plugin
fix: handle empty PDF pages in parser
docs: update CLI reference with daemon commands
perf: batch embedding for 3x indexing speedup
refactor: extract snippet highlighting into module
```

Prefixes: `feat`, `fix`, `docs`, `perf`, `refactor`, `test`, `chore`

## Pull Request Process

1. **Update documentation** if your change affects user-facing behavior
2. **Add tests** for new functionality
3. **Run the test suite** and make sure everything passes
4. **Push** to your fork and open a Pull Request
5. **Describe your changes** — what and why, not just how
6. **Link related issues** if applicable

### PR Title Format

```
feat: add support for PPTX files
fix: search crash when index is empty
```

## Reporting Bugs

Open an issue using the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md) and include:

- Steps to reproduce
- Expected vs actual behavior
- Python version and OS
- Error messages or logs

## Requesting Features

Open an issue using the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md) and describe:

- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered

## Architecture Overview

```
src/desksearch/
├── __main__.py          # CLI entry point (Click)
├── config.py            # Configuration (Pydantic)
├── api/                 # FastAPI web server
├── core/                # Search engines (BM25, dense, fusion, snippets)
├── indexer/             # Parsing, chunking, embedding, pipeline
├── plugins/             # Plugin system (base classes + loader)
└── daemon/              # Background service, tray, autostart
```

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
