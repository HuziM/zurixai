"""Cross-file reference scanning for schema definitions."""

from __future__ import annotations

import re
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
TEXT_EXTENSIONS = {
    ".ts",
    ".tsx",
    ".mts",
    ".cts",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".graphql",
    ".gql",
    ".json",
    ".yaml",
    ".yml",
    ".py",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".sql",
    ".proto",
}
MAX_RESULTS = 200


def _iter_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in TEXT_EXTENSIONS:
            yield path


def find_references(
    root: str | Path,
    name: str,
    exclude: str | Path | None = None,
    max_results: int = MAX_RESULTS,
) -> list[dict]:
    """Find word-boundary references to ``name`` under ``root``."""
    root_path = Path(root)
    if not root_path.is_dir():
        raise ValueError(f"directory not found: {root_path}")
    if not name:
        raise ValueError("name is required")

    pattern = re.compile(rf"\b{re.escape(name)}\b")
    exclude_path = Path(exclude).resolve() if exclude else None
    references: list[dict] = []

    for path in _iter_text_files(root_path):
        if exclude_path is not None and path.resolve() == exclude_path:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                references.append(
                    {
                        "file": str(path),
                        "line": line_number,
                        "snippet": line.strip()[:200],
                    }
                )
                if len(references) >= max_results:
                    return references
    return references
