"""Drift Sentinel — detects orphaned functions and dead code via git log analysis."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def check_drift(project_dir: Path) -> dict:
    """Analyze git log to find functions that haven't been modified recently."""
    result = {
        "orphaned_functions": 0,
        "orphaned_list": [],
        "stale_files": 0,
        "stale_list": [],
        "git_available": False,
    }

    # Check if git is available
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=project_dir,
            capture_output=True,
            timeout=5,
        )
        result["git_available"] = True
    except (subprocess.SubprocessError, FileNotFoundError):
        return result

    # Find all source files
    all_files = []
    for ext in ("*.py", "*.js", "*.ts", "*.jsx", "*.tsx", "*.mjs", "*.cjs"):
        for f in project_dir.glob(f"**/{ext}"):
            if any(skip in str(f) for skip in ("node_modules", ".zurix", "__pycache__", "dist", "build")):
                continue
            all_files.append(f)

    # Batch git log calls for stale file detection
    if all_files:
        stale_cutoff_days = 30
        try:
            output = subprocess.run(
                ["git", "log", "--format=%ai %H %s", "--since", f"{stale_cutoff_days} days ago"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if output.returncode == 0:
                # Parse which files were modified recently
                recently_modified = set()
                for line in output.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    # Get files changed in this commit
                    commit_hash = line.split()[3] if len(line.split()) > 3 else None
                    if commit_hash:
                        files_output = subprocess.run(
                            ["git", "diff-tree", "--no-commit-id", "-r", "--name-only", commit_hash],
                            cwd=project_dir,
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        if files_output.returncode == 0:
                            for fname in files_output.stdout.strip().split("\n"):
                                if fname:
                                    recently_modified.add(fname)

            # Check for files NOT in recently modified
            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(days=stale_cutoff_days)

            for f in all_files:
                rel_path = str(f.relative_to(project_dir))
                if rel_path not in recently_modified:
                    # Double-check with per-file git log (only for stale candidates)
                    try:
                        file_output = subprocess.run(
                            ["git", "log", "-1", "--format=%ai", "--", rel_path],
                            cwd=project_dir,
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        if file_output.returncode == 0 and file_output.stdout.strip():
                            last_date = file_output.stdout.strip().split(" ")[0]
                            file_date = datetime.strptime(last_date, "%Y-%m-%d")
                            days_since = (datetime.now() - file_date).days
                            if days_since > stale_cutoff_days:
                                result["stale_files"] += 1
                                result["stale_list"].append({
                                    "file": rel_path,
                                    "days_since_modified": days_since,
                                })
                    except Exception:
                        pass

        except Exception:
            pass

    # Find orphaned functions (defined but never called in other files OR same file)
    for f in all_files:
        try:
            content = f.read_text(errors="ignore")
            func_defs = _extract_function_names(content, f.suffix)
            for func_name in func_defs:
                # Check if function is called anywhere (including same file)
                is_called = False
                for other_f in all_files:
                    try:
                        other_content = other_f.read_text(errors="ignore")
                        if _is_function_called(func_name, other_content):
                            is_called = True
                            break
                    except Exception:
                        pass

                if not is_called and not func_name.startswith("_"):
                    result["orphaned_functions"] += 1
                    result["orphaned_list"].append(f"{func_name} in {f.relative_to(project_dir)}")
        except Exception:
            pass

    return result


def _extract_function_names(content: str, suffix: str) -> list[str]:
    """Extract function/method names from source code."""
    names = []
    if suffix == ".py":
        names = re.findall(r"^\s*(?:def|async\s+def)\s+(\w+)\s*\(", content, re.MULTILINE)
    elif suffix in (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"):
        # function declarations: function foo() / export function foo()
        names.extend(re.findall(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)", content))
        # Arrow functions assigned to const/let/var: const foo = (...) =>
        # Must have ( after = to distinguish from simple assignments
        names.extend(re.findall(r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>", content))
        names.extend(re.findall(r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function", content))
    return names


def _is_function_called(func_name: str, content: str) -> bool:
    """Check if a function name appears as a call in the content."""
    # Simple heuristic: function name followed by ( or used in import
    patterns = [
        rf"\b{re.escape(func_name)}\s*\(",  # Direct call
        rf"import\s+.*\b{re.escape(func_name)}\b",  # Import
        rf"from\s+.*\bimport\b.*\b{re.escape(func_name)}\b",  # From import
    ]
    return any(re.search(p, content) for p in patterns)
