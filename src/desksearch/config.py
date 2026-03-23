"""Configuration for DeskSearch."""
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional
import json
import os


DEFAULT_DATA_DIR = Path.home() / ".desksearch"
DEFAULT_INDEX_PATHS = [
    Path.home() / "Documents",
    Path.home() / "Desktop",
    Path.home() / "Downloads",
]
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3777


class Config(BaseModel):
    """DeskSearch configuration."""

    data_dir: Path = Field(default=DEFAULT_DATA_DIR, description="Directory to store index and metadata")
    index_paths: list[Path] = Field(default_factory=lambda: list(DEFAULT_INDEX_PATHS), description="Directories to index")
    embedding_model: str = Field(default=DEFAULT_EMBEDDING_MODEL, description="Sentence-transformer model name")
    chunk_size: int = Field(default=DEFAULT_CHUNK_SIZE, description="Characters per chunk")
    chunk_overlap: int = Field(default=DEFAULT_CHUNK_OVERLAP, description="Overlap between chunks")
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

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        """Load config from file, falling back to defaults."""
        config_path = path or (DEFAULT_DATA_DIR / "config.json")
        if config_path.exists():
            with open(config_path) as f:
                return cls(**json.load(f))
        return cls()

    def save(self, path: Optional[Path] = None) -> None:
        """Save config to file."""
        config_path = path or (self.data_dir / "config.json")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(self.model_dump(mode="json"), f, indent=2, default=str)

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
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind((self.host, self.port))
            except OSError as exc:
                issues.append(
                    f"Port {self.port} on {self.host} is not available: {exc}. "
                    "Another process may already be using it."
                )

        return issues
