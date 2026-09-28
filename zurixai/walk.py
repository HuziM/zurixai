"""Project file walking that never descends into environments, VCS or vendored code."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn",
    ".venv", "venv", "env", ".env", ".tox", ".nox", "site-packages",
    "node_modules", "bower_components", ".yarn", ".pnpm-store",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".next", ".nuxt", ".turbo", ".cache",
    "dist", "build", "out", "coverage",
    ".zurix", ".idea", ".vscode",
})


# Larger files are generated or vendored, not hand-written source; never read them.
MAX_SOURCE_BYTES = 1_000_000


def iter_source_files(project_dir: Path, suffixes: set[str]) -> Iterator[Path]:
    """Yield regular files under project_dir with one of the given suffixes, in sorted order.

    Symlinks are never followed or yielded, so a hostile repo can't point the scan elsewhere.
    """
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        for name in sorted(files):
            if Path(name).suffix not in suffixes or ".min." in name:
                continue
            path = Path(root) / name
            if path.is_symlink() or path.stat().st_size > MAX_SOURCE_BYTES:
                continue
            yield path
