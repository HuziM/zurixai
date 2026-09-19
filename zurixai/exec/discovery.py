"""Language and target discovery for micro-mock tests."""

from __future__ import annotations

import ast
import re
from pathlib import Path

_PY_EXTENSIONS = {".py"}
_JS_EXTENSIONS = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"}

_JS_FUNCTION_PATTERNS = (
    re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\("),
    re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\()"),
    re.compile(r"\b([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{"),
)


def detect_language(file_path: str | Path) -> str | None:
    """Return ``python``, ``javascript`` or ``None`` for an unknown extension."""
    suffix = Path(file_path).suffix.lower()
    if suffix in _PY_EXTENSIONS:
        return "python"
    if suffix in _JS_EXTENSIONS:
        return "javascript"
    return None


def list_functions(source: str, language: str) -> list[str]:
    """List top-level public function names in ``source``."""
    if language == "python":
        return _list_python_functions(source)
    if language == "javascript":
        return _list_javascript_functions(source)
    return []


def _list_python_functions(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            names.append(node.name)
    return names


def _list_javascript_functions(source: str) -> list[str]:
    names: list[str] = []
    for pattern in _JS_FUNCTION_PATTERNS:
        for match in pattern.finditer(source):
            name = match.group(1)
            if name and name not in names:
                names.append(name)
    return names


def find_function(source: str, language: str, function_name: str) -> bool:
    """Whether ``function_name`` is defined in ``source``."""
    return function_name in list_functions(source, language)
