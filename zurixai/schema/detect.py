"""Schema definition detection (TypeScript, GraphQL, OpenAPI, JSON Schema)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

_TS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("interface", re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)", re.MULTILINE)),
    ("type", re.compile(r"^\s*(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\s*(?:<[^>]*>)?\s*=", re.MULTILINE)),
    ("enum", re.compile(r"^\s*(?:export\s+)?enum\s+([A-Za-z_$][\w$]*)", re.MULTILINE)),
)
_GRAPHQL_PATTERN = re.compile(
    r"^\s*(type|input|enum|interface|scalar|union)\s+([A-Za-z_][\w]*)", re.MULTILINE
)
_TS_EXTENSIONS = {".ts", ".tsx", ".mts", ".cts"}
_GRAPHQL_EXTENSIONS = {".graphql", ".gql"}


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _ts_definitions(source: str) -> list[dict]:
    definitions: list[dict] = []
    for kind, pattern in _TS_PATTERNS:
        for match in pattern.finditer(source):
            definitions.append(
                {"name": match.group(1), "kind": kind, "line": _line_of(source, match.start())}
            )
    return definitions


def _graphql_definitions(source: str) -> list[dict]:
    return [
        {"name": match.group(2), "kind": match.group(1), "line": _line_of(source, match.start())}
        for match in _GRAPHQL_PATTERN.finditer(source)
    ]


def _load_structured(source: str, suffix: str) -> dict | None:
    try:
        if suffix in {".yaml", ".yml"}:
            data = yaml.safe_load(source)
        else:
            data = json.loads(source)
    except (ValueError, yaml.YAMLError):
        return None
    return data if isinstance(data, dict) else None


def _openapi_definitions(data: dict) -> list[dict] | None:
    if not ("openapi" in data or "swagger" in data):
        return None
    schemas = data.get("components", {}).get("schemas", {})
    if not isinstance(schemas, dict):
        schemas = data.get("definitions", {})
    if not isinstance(schemas, dict):
        schemas = {}
    return [{"name": name, "kind": "schema", "line": 0} for name in schemas]


def _json_schema_definitions(data: dict) -> list[dict] | None:
    has_marker = "$schema" in data or "$defs" in data or "definitions" in data
    has_inline_definition = "type" in data and "properties" in data
    if not (has_marker or has_inline_definition):
        return None
    names: list[str] = []
    for block in ("$defs", "definitions"):
        entries = data.get(block)
        if isinstance(entries, dict):
            names.extend(entries.keys())
    properties = data.get("properties")
    if isinstance(properties, dict):
        names.extend(properties.keys())
    return [{"name": name, "kind": "property", "line": 0} for name in names]


def detect_schema(file_path: str | Path) -> dict:
    """Detect the schema type and named definitions in ``file_path``."""
    path = Path(file_path)
    if not path.is_file():
        raise ValueError(f"file not found: {path}")

    source = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower()
    schema_type = "none"
    definitions: list[dict] = []

    if suffix in _TS_EXTENSIONS:
        schema_type = "typescript"
        definitions = _ts_definitions(source)
    elif suffix in _GRAPHQL_EXTENSIONS:
        schema_type = "graphql"
        definitions = _graphql_definitions(source)
    else:
        data = _load_structured(source, suffix)
        if data is not None:
            openapi = _openapi_definitions(data)
            json_schema = _json_schema_definitions(data)
            if openapi is not None:
                schema_type = "openapi"
                definitions = openapi
            elif json_schema is not None:
                schema_type = "json_schema"
                definitions = json_schema
        if schema_type == "none" and (graphql := _graphql_definitions(source)):
            schema_type = "graphql"
            definitions = graphql

    return {
        "file_path": str(path),
        "schema_type": schema_type,
        "definitions": definitions,
    }
