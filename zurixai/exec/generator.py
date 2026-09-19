"""Deterministic skeleton generation for micro-mock tests.

Produces pytest/jest-compatible skeletons from a target function signature.
The AI-generated body is stubbed with a clearly marked placeholder so the
pipeline works with no LLM configured (AI disabled).
"""

from __future__ import annotations

import re
from pathlib import Path

_IDENTIFIER = re.compile(r"^[A-Za-z_][\w]*$")

FRAMEWORKS = {"python": "pytest", "javascript": "jest"}


def _safe_identifier(name: str) -> str:
    if not _IDENTIFIER.match(name):
        raise ValueError(f"invalid function name: {name!r}")
    return name


def generate_python_test(source_path: str | Path, function_name: str) -> str:
    """Generate a pytest-compatible skeleton that imports the target module."""
    function_name = _safe_identifier(function_name)
    source_path = Path(source_path)
    module = _safe_identifier(source_path.stem)
    source_dir = source_path.resolve().parent
    return f'''"""Auto-generated micro-mock tests for {function_name} — skeleton (AI disabled)."""

from __future__ import annotations

import sys
from pathlib import Path

_SOURCE_DIR = Path({str(source_dir)!r})
if str(_SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(_SOURCE_DIR))

import {module} as _target


def test_{function_name}_exists() -> None:
    assert callable(getattr(_target, "{function_name}", None)), "{function_name} is not callable"


def test_{function_name}_placeholder() -> None:
    # TODO: AI-generated body (LLM disabled). Assert real behavior here.
    assert True


if __name__ == "__main__":
    test_{function_name}_exists()
    test_{function_name}_placeholder()
    print("PASS")
'''


def generate_javascript_test(source_path: str | Path, function_name: str) -> str:
    """Generate a jest-compatible skeleton that requires the target module."""
    function_name = _safe_identifier(function_name)
    source_path = Path(source_path).resolve()
    return f'''"use strict";
const assert = require("assert");
const target = require({str(source_path)!r});

function test_{function_name}_exists() {{
  const fn = target["{function_name}"] || (target.default && target.default["{function_name}"]);
  assert.strictEqual(typeof fn, "function", "{function_name} should be exported as a function");
}}

function test_{function_name}_placeholder() {{
  // TODO: AI-generated body (LLM disabled). Assert real behavior here.
  assert.ok(true);
}}

test_{function_name}_exists();
test_{function_name}_placeholder();
console.log("PASS");
'''


def generate_test(source_path: str | Path, function_name: str, language: str) -> dict:
    """Generate skeleton test code and metadata for ``language``."""
    if language == "python":
        code = generate_python_test(source_path, function_name)
    elif language == "javascript":
        code = generate_javascript_test(source_path, function_name)
    else:
        raise ValueError(f"unsupported language: {language!r}")
    return {
        "test_code": code,
        "framework": FRAMEWORKS[language],
        "language": language,
    }
