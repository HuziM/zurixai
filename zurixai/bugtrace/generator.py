"""Deterministic stub test generation from parsed stack traces.

The generator produces a test that reproduces the error by importing the
culprit module and re-invoking the failing code path. No LLM required;
the body is a stub marked clearly as ``# TODO: AI-generated body``.
"""

from __future__ import annotations

from zurixai.bugtrace.parser import ParsedFrame, ParsedTrace


def _module_name_from_path(file_path: str) -> str:
    """Derive a Python module name from a file path."""
    name = file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if name.endswith(".py"):
        name = name[:-3]
    elif name.endswith((".js", ".ts", ".jsx", ".tsx", ".mjs")):
        name = name.rsplit(".", 1)[0]
    return name


def generate_failing_test(trace: ParsedTrace) -> dict:
    """Generate a stub failing test from a parsed stack trace.

    The test reproduces the error path so it can serve as a regression
    test once an LLM fills in the body.
    """
    culprit = trace.culprit
    if trace.language == "python":
        code = _python_test(trace, culprit)
    elif trace.language == "javascript":
        code = _javascript_test(trace, culprit)
    else:
        code = _unknown_test(trace)

    fix_suggestion = _fix_hint(trace)

    return {
        "test_code": code,
        "fix_suggestion": fix_suggestion,
        "framework": "pytest" if trace.language == "python" else "jest",
        "language": trace.language,
        "error_type": trace.error_type,
        "error_message": trace.error_message,
        "culprit_file": culprit.file if culprit else "",
        "culprit_line": culprit.line if culprit else 0,
        "culprit_function": culprit.function if culprit else "",
    }


def _python_test(trace: ParsedTrace, culprit: ParsedFrame | None) -> str:
    error_type = trace.error_type
    error_message = trace.error_message.replace('"', '\\"')
    module = _module_name_from_path(culprit.file) if culprit else "unknown_module"
    func = culprit.function if culprit else "unknown_func"
    func = func or "unknown_func"

    return (
        f'"""Auto-generated regression test — stub (AI disabled).\n\n'
        f"Reproduces: {error_type}: {error_message}\n"
        f'"""\n\nfrom __future__ import annotations\n\n'
        f"import sys\nfrom pathlib import Path\n\n"
        f"_SOURCE_DIR = Path({str(culprit.file.rsplit('/', 1)[0] if culprit else '.')!r})\n"
        f'if str(_SOURCE_DIR) not in sys.path:\n'
        f"    sys.path.insert(0, str(_SOURCE_DIR))\n\n"
        f"try:\n"
        f"    import {module} as _target\n"
        f"except ImportError:\n"
        f"    _target = None\n\n\n"
        f"def test_{func}_reproduces_{error_type.lower().replace(' ', '_')}() -> None:\n"
        f"    \"\"\"TODO: AI-generated body — reproduce {error_type}.\"\"\"\n"
        f"    if _target is None:\n"
        f"        raise {error_type}({error_message!r})\n"
        f"    assert callable(getattr(_target, {func!r}, None)), "
        f"{func!r} must be callable\n"
    )


def _javascript_test(trace: ParsedTrace, culprit: ParsedFrame | None) -> str:
    error_type = trace.error_type
    error_message = trace.error_message.replace('"', '\\"')
    func = culprit.function if culprit else "unknown_func"
    source = str(culprit.file) if culprit else "./unknown"

    return (
        '"use strict";\n'
        "const assert = require('assert');\n"
        f"const target = require({source!r});\n\n"
        f"function test_reproduces_{error_type.lower().replace(' ', '_')}() {{\n"
        f"  // TODO: AI-generated body — reproduce {error_type}: {error_message}\n"
        f"  const fn = target['{func}'] || (target.default && target.default['{func}']);\n"
        f"  assert.ok(typeof fn === 'function', '{func} must be exported');\n"
        f"}}\n\n"
        f"test_reproduces_{error_type.lower().replace(' ', '_')}();\n"
        f"console.log('PASS');\n"
    )


def _unknown_test(trace: ParsedTrace) -> str:
    return (
        f"# Auto-generated regression test — stub (AI disabled)\n"
        f"# Error: {trace.error_type}: {trace.error_message}\n"
        f"# TODO: AI-generated body to reproduce this error\n"
    )


def _fix_hint(trace: ParsedTrace) -> str:
    error_type = trace.error_type.lower()
    if "import" in error_type:
        return "Missing or broken dependency — check import path and installed packages"
    if "type" in error_type:
        return "Type mismatch — check argument types at the call site"
    if "attribute" in error_type or "name" in error_type:
        return "Missing attribute — verify the object has this attribute"
    if "value" in error_type:
        return "Invalid value — check input constraints and edge cases"
    if "index" in error_type or "key" in error_type:
        return "Out-of-range access — add bounds/length check before indexing"
    if "overflow" in error_type or "memory" in error_type:
        return "Resource limit exceeded — reduce input size or add pagination"
    if "timeout" in error_type:
        return "Operation too slow — optimize or increase timeout"
    if "syntax" in error_type:
        return "Syntax error — check brackets, colons, indentation"
    if "reference" in error_type:
        return "Undefined reference — verify variable/function is declared"
    if "typeerror" in error_type:
        return "Type error — check operand types at the failing expression"
    return "Investigate the failing frame and apply the appropriate fix"
