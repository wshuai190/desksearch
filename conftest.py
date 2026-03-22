"""Root conftest — wire up `src/desksearch/` as `desksearch` package for tests."""
import sys
from pathlib import Path

_src = str(Path(__file__).resolve().parent / "src")

if _src not in sys.path:
    sys.path.insert(0, _src)
