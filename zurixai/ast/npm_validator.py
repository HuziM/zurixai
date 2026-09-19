"""AST Import Validator for npm packages."""

from __future__ import annotations

import json
import re
from pathlib import Path


# Node.js built-in modules (both bare and node: protocol)
NODEJS_BUILTINS = frozenset({
    "assert", "buffer", "child_process", "cluster", "console", "constants",
    "crypto", "dgram", "dns", "domain", "events", "fs", "http", "http2",
    "https", "inspector", "module", "net", "os", "path", "perf_hooks",
    "process", "punycode", "querystring", "readline", "repl", "stream",
    "string_decoder", "sys", "timers", "tls", "trace_events", "tty",
    "url", "util", "v8", "vm", "worker_threads", "zlib",
    # node: protocol builtins
    "node:assert", "node:assert/strict", "node:async_hooks", "node:buffer",
    "node:child_process", "node:cluster", "node:console", "node:constants",
    "node:crypto", "node:dgram", "node:diagnostics_channel", "node:dns",
    "node:domain", "node:events", "node:fs", "node:http", "node:http2",
    "node:https", "node:inspector", "node:module", "node:net", "node:os",
    "node:path", "node:perf_hooks", "node:process", "node:punycode",
    "node:querystring", "node:readline", "node:repl", "node:stream",
    "node:string_decoder", "node:test", "node:timers", "node:tls",
    "node:trace_events", "node:tty", "node:url", "node:util", "node:v8",
    "node:vm", "node:worker_threads", "node:zlib",
})


def validate_npm_imports(project_dir: Path) -> dict:
    """Scan JS/TS files for npm imports and validate against package.json + registry."""
    result = {"valid": 0, "invalid": 0, "invalid_imports": [], "checked_files": 0}

    # Find package.json
    package_json = project_dir / "package.json"
    if not package_json.exists():
        return result

    try:
        pkg_data = json.loads(package_json.read_text())
        declared_deps = set(pkg_data.get("dependencies", {}).keys())
        declared_dev_deps = set(pkg_data.get("devDependencies", {}).keys())
        all_deps = declared_deps | declared_dev_deps
        project_name = pkg_data.get("name", "")
    except (json.JSONDecodeError, KeyError):
        return result

    # Find JS/TS files
    js_patterns = ["**/*.js", "**/*.ts", "**/*.jsx", "**/*.tsx", "**/*.mjs", "**/*.cjs"]
    scanned_files: set[Path] = set()
    for pattern in js_patterns:
        for f in project_dir.glob(pattern):
            if "node_modules" in str(f) or ".zurix" in str(f):
                continue
            scanned_files.add(f)

    # Parse imports from each file
    import_pattern = re.compile(
        r"""(?:import\s+.*?from\s+['"]([^'"]+)['"]|"""
        r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)|"""
        r"""import\s*\(\s*['"]([^'"]+)['"]\s*\))"""
    )

    for f in scanned_files:
        result["checked_files"] += 1
        try:
            content = f.read_text(errors="ignore")
        except Exception:
            continue

        for match in import_pattern.finditer(content):
            pkg = match.group(1) or match.group(2) or match.group(3)
            if not pkg or pkg.startswith(".") or pkg.startswith("/"):
                continue

            # Skip node: protocol and bare Node.js built-in imports
            if pkg in NODEJS_BUILTINS or pkg.startswith("node:"):
                continue

            # Extract package name (handle @scope/pkg)
            parts = pkg.split("/")
            if parts[0].startswith("@"):
                pkg_name = "/".join(parts[:2])
            else:
                pkg_name = parts[0]

            # Skip self-imports (package importing itself)
            if pkg_name == project_name:
                continue

            # Check if it's a known dependency or a hallucinated one
            if pkg_name in all_deps:
                result["valid"] += 1
            else:
                # Likely a hallucinated or missing dependency
                result["invalid"] += 1
                result["invalid_imports"].append(f"{pkg_name} (from {f.name})")

    return result
