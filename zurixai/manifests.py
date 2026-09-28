"""Declared-dependency parsing for Python projects."""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

from zurixai.walk import iter_source_files

_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_VCS_PREFIX = re.compile(r"^(git|hg|svn|bzr)\+", re.IGNORECASE)


def normalize_name(name: str) -> str:
    """PEP 503 normalized distribution name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def distribution_spellings(import_root: str) -> tuple[str, ...]:
    """Common PyPI names for a module whose distribution name isn't the import name."""
    name = normalize_name(import_root)
    return (name, f"{name}-py", f"py{name}", f"python-{name}")


def _requirement_name(spec: str) -> str | None:
    match = _REQ_NAME.match(spec)
    return normalize_name(match.group(1)) if match else None


def _from_specs(specs: object) -> set[str]:
    names: set[str] = set()
    if isinstance(specs, list):
        for spec in specs:
            if isinstance(spec, str) and (name := _requirement_name(spec)):
                names.add(name)
    return names


def _from_pyproject(path: Path) -> set[str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (tomllib.TOMLDecodeError, OSError):
        return set()

    names: set[str] = set()
    names |= _from_specs(data.get("build-system", {}).get("requires"))
    project = data.get("project", {})
    names |= _from_specs(project.get("dependencies"))
    for group in (project.get("optional-dependencies") or {}).values():
        names |= _from_specs(group)
    for group in (data.get("dependency-groups") or {}).values():
        names |= _from_specs(group)

    poetry = data.get("tool", {}).get("poetry", {})
    poetry_tables = [poetry.get("dependencies"), poetry.get("dev-dependencies")]
    poetry_tables += [g.get("dependencies") for g in (poetry.get("group") or {}).values()]
    for table in poetry_tables:
        if isinstance(table, dict):
            names |= {normalize_name(k) for k in table if k.lower() != "python"}
    return names


def _from_requirements(path: Path) -> set[str]:
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith(("-", ".", "/")):
            continue
        first_token = line.split("@", 1)[0].strip()
        if "://" in first_token or _VCS_PREFIX.match(first_token):
            continue  # bare URL / VCS requirement: no package name to read
        if name := _requirement_name(line):
            names.add(name)
    return names


def _from_setup_py(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.keyword)
            and node.arg in ("install_requires", "tests_require")
            and isinstance(node.value, (ast.List, ast.Tuple))
        ):
            names |= _from_specs([
                elt.value for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            ])
    return names


def python_declared_deps(project_dir: Path) -> set[str]:
    """Normalized names of every dependency declared anywhere in the project's manifests."""
    names: set[str] = set()
    if (pyproject := project_dir / "pyproject.toml").is_file():
        names |= _from_pyproject(pyproject)
    for req in iter_source_files(project_dir, {".txt"}):
        if "requirements" in req.name:
            names |= _from_requirements(req)
    if (setup_py := project_dir / "setup.py").is_file():
        names |= _from_setup_py(setup_py)
    return names


def python_project_name(project_dir: Path) -> str | None:
    """Normalized project name from pyproject.toml, if declared."""
    pyproject = project_dir / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="replace"))
    except tomllib.TOMLDecodeError:
        return None
    name = data.get("project", {}).get("name") or data.get("tool", {}).get("poetry", {}).get("name")
    return normalize_name(name) if isinstance(name, str) else None
