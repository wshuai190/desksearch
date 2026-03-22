"""Document parsers for various file formats.

Registry-based parser system. Each parser is a callable that takes a file path
and returns extracted plain text. New parsers can be added via register_parser().
"""
import logging
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Parser type: takes a Path, returns extracted text
ParserFunc = Callable[[Path], str]

# Registry mapping extensions to parser functions
_PARSERS: dict[str, ParserFunc] = {}

# Code file extensions for language detection
CODE_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c-header",
    ".go": "go",
    ".rs": "rust",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".sql": "sql",
    ".r": "r",
    ".R": "r",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".lua": "lua",
    ".pl": "perl",
    ".php": "php",
}


def register_parser(extensions: list[str], parser: ParserFunc) -> None:
    """Register a parser function for one or more file extensions."""
    for ext in extensions:
        _PARSERS[ext.lower()] = parser


def get_parser(extension: str) -> Optional[ParserFunc]:
    """Get the parser for a given file extension."""
    return _PARSERS.get(extension.lower())


def parse_file(path: Path) -> Optional[str]:
    """Parse a file and return its text content.

    Args:
        path: Path to the file to parse.

    Returns:
        Extracted text, or None if the file cannot be parsed.
    """
    ext = path.suffix.lower()
    parser = get_parser(ext)
    if parser is None:
        logger.warning("No parser registered for extension: %s", ext)
        return None
    try:
        text = parser(path)
        if text and text.strip():
            return text.strip()
        logger.warning("Parser returned empty text for: %s", path)
        return None
    except Exception:
        logger.exception("Failed to parse file: %s", path)
        return None


# --- Built-in parsers ---


def _parse_text(path: Path) -> str:
    """Parse plain text files (txt, md, rst, org, csv, tsv, etc.)."""
    return path.read_text(encoding="utf-8", errors="replace")


def _parse_pdf(path: Path) -> str:
    """Parse PDF files using PyMuPDF (fitz)."""
    import fitz

    pages = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            text = page.get_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)


def _parse_docx(path: Path) -> str:
    """Parse DOCX files using python-docx."""
    from docx import Document

    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def _parse_code(path: Path) -> str:
    """Parse code files with language metadata prefix."""
    ext = path.suffix.lower()
    language = CODE_EXTENSIONS.get(ext, "unknown")
    content = path.read_text(encoding="utf-8", errors="replace")
    return f"[{language}] {path.name}\n\n{content}"


def _parse_html(path: Path) -> str:
    """Parse HTML files, extracting text content."""
    from bs4 import BeautifulSoup

    raw = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "html.parser")
    # Remove script and style elements
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _parse_json_yaml(path: Path) -> str:
    """Parse JSON/YAML/TOML as plain text (structure is content)."""
    return path.read_text(encoding="utf-8", errors="replace")


def _parse_ipynb(path: Path) -> str:
    """Parse Jupyter notebooks, extracting markdown and code cells."""
    import json

    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    parts = []
    for cell in data.get("cells", []):
        cell_type = cell.get("cell_type", "")
        source = "".join(cell.get("source", []))
        if cell_type == "markdown":
            parts.append(source)
        elif cell_type == "code":
            parts.append(f"```\n{source}\n```")
    return "\n\n".join(parts)


# --- Register built-in parsers ---

register_parser([".txt", ".md", ".rst", ".org", ".tex"], _parse_text)
register_parser([".csv", ".tsv"], _parse_text)
register_parser([".pdf"], _parse_pdf)
register_parser([".docx", ".doc"], _parse_docx)
register_parser([".html", ".htm", ".xml"], _parse_html)
register_parser([".json", ".yaml", ".yml", ".toml"], _parse_json_yaml)
register_parser([".ipynb"], _parse_ipynb)
register_parser(list(CODE_EXTENSIONS.keys()), _parse_code)
