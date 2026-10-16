"""Configuration for DeskSearch."""
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional
import json
import logging
import os

logger = logging.getLogger(__name__)


def default_data_dir() -> Path:
    """Resolve the data directory, honouring ``DESKSEARCH_DATA_DIR`` at call time.

    Reading the environment lazily (instead of once at import) keeps the
    override working for embedders, Click's test runner and any launcher that
    sets the variable after ``desksearch`` has been imported.
    """
    return Path(os.environ.get("DESKSEARCH_DATA_DIR", str(Path.home() / ".desksearch")))


# Retained for backwards compatibility; prefer default_data_dir() for new code.
DEFAULT_DATA_DIR = default_data_dir()
DEFAULT_INDEX_PATHS = [
    Path.home() / "Documents",
    Path.home() / "Desktop",
    Path.home() / "Downloads",
]
DEFAULT_EMBEDDING_MODEL = "ielabgroup/Starbucks-msmarco"

# Starbucks 2D Matryoshka speed tiers: (num_layers, embedding_dim)
# From the paper: "Starbucks: Improved Training for 2D Matryoshka Embeddings" (ECIR 2026)
STARBUCKS_TIERS = {
    "fast": (2, 32),       # ~3x faster, tiny index, good for local file search
    "middle": (4, 64),     # balanced speed/quality
    "pro": (6, 128),       # max quality (6 layers saved locally, nothing larger needed)
}
DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3777


class Config(BaseModel):
    """DeskSearch configuration."""

    data_dir: Path = Field(default_factory=default_data_dir, description="Directory to store index and metadata")
    index_paths: list[Path] = Field(default_factory=lambda: list(DEFAULT_INDEX_PATHS), description="Directories to index")
    embedding_model: str = Field(default=DEFAULT_EMBEDDING_MODEL, description="Embedding model (default: Starbucks 2D Matryoshka)")
    chunk_size: int = Field(default=DEFAULT_CHUNK_SIZE, description="Characters per chunk")
    chunk_overlap: int = Field(default=DEFAULT_CHUNK_OVERLAP, description="Overlap between chunks")
    search_speed: str = Field(
        default="middle",
        description="Search speed tier: 'fast' (2-layer, 32d), 'middle' (4-layer, 64d), 'pro' (6-layer, 128d)",
    )
    embedding_dim: int = Field(
        default=64,
        description="Embedding dimensions (auto-set by search_speed tier). Override manually if needed.",
    )
    embedding_layers: int = Field(
        default=4,
        description="Number of transformer layers (auto-set by search_speed tier). Override manually if needed.",
    )
    host: str = Field(default=DEFAULT_HOST, description="API server host")
    port: int = Field(default=DEFAULT_PORT, description="API server port")
    file_extensions: list[str] = Field(
        default_factory=lambda: [
            # Documents
            ".txt", ".md", ".pdf", ".docx", ".doc", ".pptx", ".ppt",
            ".xlsx", ".xls", ".epub", ".rtf",
            # Code
            ".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".go", ".rs",
            ".rb", ".swift", ".kt", ".scala", ".lua", ".pl", ".php",
            # Web / data
            ".html", ".htm", ".xml", ".json", ".yaml", ".yml", ".toml",
            ".csv", ".tsv",
            # Academic / writing
            ".tex", ".rst", ".org", ".ipynb",
            # Shell / config
            ".sh", ".bash", ".zsh", ".sql",
            ".log", ".cfg", ".ini", ".conf", ".env",
            ".r", ".R",
            # Email
            ".eml", ".msg",
            # Archives (text files inside are extracted)
            ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz",
        ],
        description="File extensions to index",
    )
    max_file_size_mb: int = Field(default=50, description="Skip files larger than this (MB)")
    enabled_plugins: list[str] = Field(
        default_factory=list,
        description="Plugin names to enable (empty list = all discovered plugins)",
    )
    plugin_config: dict[str, dict] = Field(
        default_factory=dict,
        description="Per-plugin configuration keyed by plugin name",
    )
    # ---------------------------------------------------------------------------
    # Integration settings (all optional — zero impact if not configured)
    # ---------------------------------------------------------------------------
    api_key: Optional[str] = Field(
        default=None,
        description="Bearer token for /api/v1/search and integration endpoints. "
                    "If unset, those endpoints are open (no auth).",
    )
    slack_webhook_url: Optional[str] = Field(
        default=None,
        description="Incoming webhook URL for posting Slack notifications (optional).",
    )
    webhook_urls: list[str] = Field(
        default_factory=list,
        description="HTTP(S) URLs to POST to when indexing completes or new files are found.",
    )

    excluded_dirs: list[str] = Field(
        default_factory=lambda: [
            ".git", "__pycache__", "node_modules", ".venv", "venv",
            ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
            ".desksearch", ".Trash",
        ],
        description="Directory names to skip during indexing",
    )

    def resolve_starbucks_tier(self) -> tuple[int, int]:
        """Return (num_layers, embedding_dim) based on search_speed tier.

        If search_speed is a known tier, returns its preset values.
        Otherwise uses embedding_layers and embedding_dim directly.
        """
        if self.search_speed in STARBUCKS_TIERS:
            layers, dim = STARBUCKS_TIERS[self.search_speed]
            self.embedding_layers = layers
            self.embedding_dim = dim
            return layers, dim
        return self.embedding_layers, self.embedding_dim

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        """Load config from file, falling back to defaults.

        The file is read as ``utf-8-sig`` so a UTF-8 BOM is tolerated —
        Windows PowerShell 5.1 (``Set-Content -Encoding UTF8``), Notepad and
        several editors add one, and ``json.load`` would otherwise raise
        "Unexpected UTF-8 BOM" and take the whole app down at startup.

        A missing, unreadable or malformed file is not fatal either: the
        defaults are used and a warning is logged.
        """
        config_path = path or (default_data_dir() / "config.json")
        if not config_path.exists():
            return cls()
        try:
            with open(config_path, encoding="utf-8-sig") as f:
                return cls(**json.load(f))
        except Exception as exc:  # noqa: BLE001 — never block startup on config
            logger.warning(
                "Could not read config %s (%s: %s) — using defaults. "
                "The file was left untouched.",
                config_path,
                type(exc).__name__,
                exc,
            )
            return cls()

    def save(self, path: Optional[Path] = None) -> None:
        """Save config to file (UTF-8, no BOM, written atomically).

        The encoding is explicit because ``open()`` otherwise uses the locale
        encoding on Windows (e.g. cp936), which would corrupt non-ASCII paths.
        """
        config_path = path or (self.data_dir / "config.json")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = config_path.with_suffix(config_path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(mode="json"), f, indent=2, default=str)
        os.replace(tmp_path, config_path)

    def validate(self) -> list[str]:
        """Validate configuration and return a list of warning/error strings.

        Does NOT raise — callers should log the returned messages and decide
        whether to abort.  An empty list means everything looks fine.
        """
        import socket
        issues: list[str] = []

        # chunk_overlap must be smaller than chunk_size
        if self.chunk_overlap >= self.chunk_size:
            issues.append(
                f"chunk_overlap ({self.chunk_overlap}) must be less than "
                f"chunk_size ({self.chunk_size})"
            )

        # data_dir must be creatable
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            issues.append(f"Cannot create data_dir {self.data_dir}: {exc}")

        # Warn about missing index_paths (they may be created later)
        for p in self.index_paths:
            expanded = Path(str(p)).expanduser()
            if not expanded.exists():
                issues.append(f"Index path does not exist (will be skipped): {p}")

        # Check port availability
        if self.port < 1 or self.port > 65535:
            issues.append(f"Invalid port number: {self.port}")
        else:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    if os.name == "nt":
                        # Windows: SO_REUSEADDR lets us bind a port another
                        # process already owns, which would silently disable
                        # this check. SO_EXCLUSIVEADDRUSE restores the
                        # Unix-like "is the port actually free?" semantics.
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                    else:
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind((self.host, self.port))
            except OSError as exc:
                issues.append(
                    f"Port {self.port} on {self.host} is not available: {exc}. "
                    "Another process may already be using it."
                )

        return issues
