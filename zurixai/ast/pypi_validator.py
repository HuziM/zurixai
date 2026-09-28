"""AST Import Validator for PyPI packages."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from zurixai.manifests import (
    distribution_spellings,
    normalize_name,
    python_declared_deps,
    python_project_name,
)
from zurixai.walk import SKIP_DIRS, iter_source_files

# Removed from newer Pythons (PEP 594, distutils, imp, asyncore…) — still stdlib for older
# targets, so results must not depend on the interpreter running the check.
REMOVED_STDLIB = frozenset({
    "aifc", "asynchat", "asyncore", "audioop", "cgi", "cgitb", "chunk", "crypt", "distutils",
    "imghdr", "imp", "lib2to3", "mailcap", "msilib", "nis", "nntplib", "ossaudiodev", "pipes",
    "smtpd", "sndhdr", "spwd", "sunau", "telnetlib", "uu", "xdrlib",
})
STDLIB = frozenset(sys.stdlib_module_names) | REMOVED_STDLIB | {"__future__"}

# Import name → distribution name(s) where they differ.
IMPORT_TO_DIST: dict[str, tuple[str, ...]] = {
    "PIL": ("pillow",),
    "cv2": ("opencv-python", "opencv-python-headless", "opencv-contrib-python"),
    "sklearn": ("scikit-learn",),
    "skimage": ("scikit-image",),
    "yaml": ("pyyaml",),
    "attr": ("attrs",),
    "bs4": ("beautifulsoup4",),
    "dateutil": ("python-dateutil",),
    "dotenv": ("python-dotenv",),
    "jwt": ("pyjwt",),
    "magic": ("python-magic",),
    "Crypto": ("pycryptodome", "pycryptodomex"),
    "OpenSSL": ("pyopenssl",),
    "git": ("gitpython",),
    "github": ("pygithub",),
    "pdm": ("pdm", "pdm-backend"),
    "serial": ("pyserial",),
    "usb": ("pyusb",),
    "docx": ("python-docx",),
    "pptx": ("python-pptx",),
    "zmq": ("pyzmq",),
    "MySQLdb": ("mysqlclient",),
    "psycopg2": ("psycopg2", "psycopg2-binary"),
    "google": ("protobuf", "google-api-python-client", "google-cloud-core"),
    "gi": ("pygobject",),
    "win32api": ("pywin32",),
    "typing_extensions": ("typing-extensions",),
}


def _distribution_candidates(root: str) -> tuple[str, ...]:
    return IMPORT_TO_DIST.get(root, distribution_spellings(root))


def _has_python(folder: Path) -> bool:
    return next(iter_source_files(folder, {".py"}), None) is not None


def _local_roots(project_dir: Path) -> set[str]:
    """Top-level module names that belong to the project itself (root and src/ layout)."""
    roots: set[str] = set()
    for base in (project_dir, project_dir / "src"):
        if not base.is_dir():
            continue
        for child in base.iterdir():
            if child.is_dir() and child.name not in SKIP_DIRS and not child.name.startswith("."):
                if _has_python(child):
                    roots.add(child.name)
            elif child.suffix == ".py":
                roots.add(child.stem)
    return roots


def _is_sibling_module(root: str, source_file: Path) -> bool:
    folder = source_file.parent
    return (folder / f"{root}.py").is_file() or ((folder / root).is_dir() and _has_python(folder / root))


_IMPORT_ERRORS = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}


def _handles_import_error(node: ast.Try) -> bool:
    for handler in node.handlers:
        if handler.type is None:
            return True
        types = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
        if any(isinstance(t, (ast.Name, ast.Attribute)) and ast.unparse(t).split(".")[-1] in _IMPORT_ERRORS
               for t in types):
            return True
    return False


def _is_type_checking(test: ast.expr) -> bool:
    return ast.unparse(test).split(".")[-1] == "TYPE_CHECKING"


class _ImportCollector(ast.NodeVisitor):
    """Collects (root, optional) pairs; skips TYPE_CHECKING-only imports."""

    def __init__(self) -> None:
        self.imports: list[tuple[str, bool]] = []
        self._optional = 0

    def visit_Try(self, node: ast.Try) -> None:
        guarded = _handles_import_error(node)
        self._optional += guarded
        for child in (*node.body, *node.handlers):
            self.visit(child)
        self._optional -= guarded
        for child in (*node.orelse, *node.finalbody):
            self.visit(child)

    visit_TryStar = visit_Try  # type: ignore[assignment]

    def visit_If(self, node: ast.If) -> None:
        if _is_type_checking(node.test):
            for child in node.orelse:
                self.visit(child)
            return
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        self.imports.extend((alias.name.split(".")[0], self._optional > 0) for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and node.level == 0:
            self.imports.append((node.module.split(".")[0], self._optional > 0))


def _collect_imports(tree: ast.AST) -> list[tuple[str, bool]]:
    collector = _ImportCollector()
    collector.visit(tree)
    return collector.imports


def validate_pypi_imports(project_dir: Path) -> dict:
    """Scan Python files for imports and validate them against the project's declared deps."""
    result: dict = {"valid": 0, "invalid": 0, "invalid_imports": [], "undeclared": {}, "checked_files": 0}

    declared = python_declared_deps(project_dir)
    project_name = python_project_name(project_dir)
    local_roots = _local_roots(project_dir)

    parsed: list[tuple[Path, list[tuple[str, bool]]]] = []
    for source in iter_source_files(project_dir, {".py"}):
        result["checked_files"] += 1
        try:
            tree = ast.parse(source.read_text(encoding="utf-8", errors="ignore"))
        except (SyntaxError, ValueError):
            continue
        parsed.append((source, _collect_imports(tree)))

    # A module imported under an ImportError guard anywhere is optional everywhere.
    optional_roots = {root for _, imports in parsed for root, optional in imports if optional}

    for source, imports in parsed:
        rel = source.relative_to(project_dir).as_posix()
        for root, _ in imports:
            if root in optional_roots or root in STDLIB or root.startswith("_"):
                continue
            if root in local_roots or normalize_name(root) == project_name or _is_sibling_module(root, source):
                continue

            candidates = _distribution_candidates(root)
            if any(c in declared for c in candidates) or normalize_name(root) in declared:
                result["valid"] += 1
                continue

            result["invalid"] += 1
            result["invalid_imports"].append(f"{root} (from {source.name})")
            entry = result["undeclared"].setdefault(root, {"package": candidates[0], "files": []})
            if rel not in entry["files"]:
                entry["files"].append(rel)

    return result
