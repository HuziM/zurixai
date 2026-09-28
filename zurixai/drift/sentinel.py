"""Drift Sentinel — orphaned functions and stale files."""

from __future__ import annotations

import ast
import re
import subprocess
import time
from collections import Counter
from pathlib import Path

from zurixai.walk import iter_source_files

SOURCE_SUFFIXES = {".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"}
STALE_AFTER_DAYS = 30

_IDENTIFIER = re.compile(r"[A-Za-z_$][\w$]*")
_JS_FUNCTION = re.compile(r"(?<!export )(?<!export async )(?<!default )\bfunction\s+([A-Za-z_$][\w$]*)\s*\(")
_JS_ARROW = re.compile(
    r"(?<!export )\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"
)


def _python_candidates(source: str) -> list[str]:
    """Undecorated module-level functions that aren't private or tests."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    return [
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.decorator_list
        and not node.name.startswith(("_", "test"))
    ]


def _js_candidates(source: str) -> list[str]:
    names = _JS_FUNCTION.findall(source) + _JS_ARROW.findall(source)
    return [n for n in names if not n.startswith("_")]


def _find_orphans(project_dir: Path, files: list[Path]) -> list[str]:
    references: Counter[str] = Counter()
    definitions: Counter[str] = Counter()
    candidates: list[tuple[str, Path]] = []

    for path in files:
        source = path.read_text(encoding="utf-8", errors="ignore")
        references.update(_IDENTIFIER.findall(source))
        names = _python_candidates(source) if path.suffix == ".py" else _js_candidates(source)
        definitions.update(names)
        candidates.extend((name, path) for name in names)

    return [
        f"{name} in {path.relative_to(project_dir).as_posix()}"
        for name, path in candidates
        if references[name] - definitions[name] <= 0
    ]


def _is_git_worktree(project_dir: Path) -> bool:
    try:
        probe = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=project_dir, capture_output=True, text=True, timeout=5, check=False,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return False
    return probe.returncode == 0 and probe.stdout.strip() == "true"


def _is_shallow(project_dir: Path) -> bool:
    try:
        probe = subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            cwd=project_dir, capture_output=True, text=True, timeout=5, check=False,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return False
    return probe.stdout.strip() == "true"


def _last_commit_times(project_dir: Path) -> dict[str, int]:
    """Last commit time per file (paths relative to project_dir), from one `git log`."""
    try:
        log = subprocess.run(
            ["git", "log", "--relative", "--name-only", "--format=%x00%ct", "--", "."],
            cwd=project_dir, capture_output=True, text=True, timeout=60, check=False,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return {}
    if log.returncode != 0:
        return {}

    times: dict[str, int] = {}
    for block in log.stdout.split("\x00"):
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines or not lines[0].isdigit():
            continue
        commit_time = int(lines[0])
        for name in lines[1:]:
            times.setdefault(name, commit_time)
    return times


def check_drift(project_dir: Path) -> dict:
    """Find orphaned functions and files untouched for more than STALE_AFTER_DAYS."""
    files = list(iter_source_files(project_dir, SOURCE_SUFFIXES))
    orphans = _find_orphans(project_dir, files)
    result: dict = {
        "orphaned_functions": len(orphans),
        "orphaned_list": orphans,
        "stale_files": 0,
        "stale_list": [],
        "git_available": _is_git_worktree(project_dir),
    }
    if not result["git_available"]:
        return result
    if _is_shallow(project_dir):
        # Every file shares the single fetched commit's date, so "stale" would mean nothing.
        result["stale_skipped"] = "shallow clone"
        return result

    last_commit = _last_commit_times(project_dir)
    now = time.time()
    for path in files:
        rel = path.relative_to(project_dir).as_posix()
        if (committed := last_commit.get(rel)) is None:
            continue
        days = int((now - committed) // 86400)
        if days > STALE_AFTER_DAYS:
            result["stale_list"].append({"file": rel, "days_since_modified": days})
    result["stale_files"] = len(result["stale_list"])
    return result
