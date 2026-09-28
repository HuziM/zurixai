"""Centralized configuration for ZurixAI CLI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Immutable CLI configuration. Loaded from env vars + ~/.zurix/config.json."""

    # --- Local paths ---
    config_dir: str = ""
    rules_file: str = ""

    # --- Output ---
    verbose: bool = False
    json_output: bool = False

    @classmethod
    def from_env(cls) -> Config:
        config_dir = str(Path.home() / ".zurix")
        return cls(
            config_dir=config_dir,
            rules_file=os.getenv("ZURIX_RULES_FILE", ".zurix/rules.md"),
            verbose=os.getenv("ZURIX_VERBOSE", "0") == "1",
            json_output=os.getenv("ZURIX_JSON", "0") == "1",
        )

    def ensure_dirs(self) -> None:
        Path(self.config_dir).mkdir(parents=True, exist_ok=True)


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.from_env()
        _config.ensure_dirs()
    return _config
