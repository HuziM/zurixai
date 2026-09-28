"""AST Import Validator for npm packages."""

from __future__ import annotations

import json
import re
from pathlib import Path

from zurixai.walk import iter_source_files

NODEJS_BUILTINS = frozenset({
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console", "constants",
    "crypto", "dgram", "diagnostics_channel", "dns", "domain", "events", "fs", "http", "http2",
    "https", "inspector", "module", "net", "os", "path", "perf_hooks", "process", "punycode",
    "querystring", "readline", "repl", "stream", "string_decoder", "sys", "test", "timers",
    "tls", "trace_events", "tty", "url", "util", "v8", "vm", "wasi", "worker_threads", "zlib",
})

JS_SUFFIXES = {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".mts", ".cts"}

_SPEC = r"""['"]([^'"\n]+)['"]"""
IMPORT_PATTERN = re.compile(
    rf"""\bimport\s+(?:type\s+)?[^'";]*?\bfrom\s*{_SPEC}"""  # import x / { a,\n b } from 'p'
    rf"""|\bexport\s+[^'";]*?\bfrom\s*{_SPEC}"""             # export { a } / * from 'p'
    rf"""|\bimport\s*{_SPEC}"""                              # import 'p' (side effect)
    rf"""|\brequire\s*\(\s*{_SPEC}\s*\)"""                   # require('p')
    rf"""|\bimport\s*\(\s*{_SPEC}\s*\)"""                    # import('p')
)

_DEP_FIELDS = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
_COMMENTS = re.compile(r"/\*.*?\*/|^\s*//[^\n]*", re.DOTALL | re.MULTILINE)
_VALID_NAME = re.compile(r"^(?:@[A-Za-z0-9][\w.~-]*/)?[A-Za-z0-9][\w.~-]*$")


def _package_name(specifier: str) -> str:
    parts = specifier.split("/")
    return "/".join(parts[:2]) if parts[0].startswith("@") else parts[0]


def _load_manifests(project_dir: Path) -> dict[Path, dict]:
    """Every package.json in the project (monorepo sub-packages included), keyed by directory."""
    manifests: dict[Path, dict] = {}
    for path in iter_source_files(project_dir, {".json"}):
        if path.name != "package.json":
            continue
        try:
            manifests[path.parent] = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
    return manifests


def _declared_for(source: Path, project_dir: Path, manifests: dict[Path, dict]) -> set[str]:
    """Deps declared in package.json files from the source's folder up to the project root."""
    declared: set[str] = set()
    folder = source.parent
    while True:
        data = manifests.get(folder, {})
        declared.update(name for field in _DEP_FIELDS for name in (data.get(field) or {}))
        if folder == project_dir or project_dir not in folder.parents:
            return declared
        folder = folder.parent


def validate_npm_imports(project_dir: Path) -> dict:
    """Scan JS/TS files for package imports and validate them against package.json."""
    result: dict = {"valid": 0, "invalid": 0, "invalid_imports": [], "undeclared": {}, "checked_files": 0}

    if not (project_dir / "package.json").exists():
        return result
    manifests = _load_manifests(project_dir)
    local_names = {data["name"] for data in manifests.values() if isinstance(data.get("name"), str)}

    for source in iter_source_files(project_dir, JS_SUFFIXES):
        result["checked_files"] += 1
        try:
            content = _COMMENTS.sub("", source.read_text(errors="ignore"))
        except OSError:
            continue

        declared = _declared_for(source, project_dir, manifests)
        rel = source.relative_to(project_dir).as_posix()
        for match in IMPORT_PATTERN.finditer(content):
            specifier = next(g for g in match.groups() if g)
            if specifier.startswith((".", "/")) or ":" in specifier:
                continue
            if specifier.split("/")[0] in NODEJS_BUILTINS:
                continue

            name = _package_name(specifier)
            if not _VALID_NAME.match(name) or name in local_names:
                continue
            if name in declared:
                result["valid"] += 1
                continue

            result["invalid"] += 1
            result["invalid_imports"].append(f"{name} (from {source.name})")
            entry = result["undeclared"].setdefault(name, {"package": name, "files": []})
            if rel not in entry["files"]:
                entry["files"].append(rel)

    return result
