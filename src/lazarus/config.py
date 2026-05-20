"""Global configuration for Lazarus."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_base_dir() -> Path:
    return Path(os.environ.get("LAZARUS_HOME", Path.home() / ".lazarus"))


@dataclass
class LazarusConfig:
    base_dir: Path = field(default_factory=_default_base_dir)
    python_target: str = "3.14"
    python_binary: str = "python3.14"

    # Server
    devpi_url: str = "http://localhost:3141"
    devpi_index: str = "lazarus/packages"
    devpi_user: str = "lazarus"
    devpi_password: str = ""
    upload_enabled: bool = False

    # Claude API
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-5-20241022"
    max_tokens_per_fix: int = 8192

    # Processing
    max_attempts: int = 3
    test_timeout: int = 300
    batch_size: int = 50

    @property
    def db_path(self) -> Path:
        return self.base_dir / "queue.db"

    @property
    def work_dir(self) -> Path:
        return self.base_dir / "work"

    @property
    def cache_dir(self) -> Path:
        return self.base_dir / "cache"

    def ensure_dirs(self) -> None:
        """Create all required directories."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> LazarusConfig:
        """Load config from environment variables."""
        config = cls()
        config.devpi_password = os.environ.get("LAZARUS_DEVPI_PASSWORD", "")
        config.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        config.upload_enabled = os.environ.get("LAZARUS_UPLOAD", "").lower() in (
            "1", "true", "yes",
        )
        if url := os.environ.get("LAZARUS_DEVPI_URL"):
            config.devpi_url = url
        if index := os.environ.get("LAZARUS_DEVPI_INDEX"):
            config.devpi_index = index
        if model := os.environ.get("LAZARUS_CLAUDE_MODEL"):
            config.claude_model = model
        if target := os.environ.get("LAZARUS_PYTHON_TARGET"):
            config.python_target = target
        if binary := os.environ.get("LAZARUS_PYTHON_BINARY"):
            config.python_binary = binary
        return config
