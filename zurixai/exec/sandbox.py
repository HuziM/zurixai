"""Sandboxed subprocess execution for generated micro-mock tests.

Runs untrusted generated tests in an isolated temp directory with a hard
timeout. No network policy, no shell, output is truncated.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TIMEOUT = 15
MAX_OUTPUT = 20000


@dataclass
class ExecResult:
    """Outcome of a sandboxed test run."""

    passed: bool
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_s: float = 0.0

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "duration_s": self.duration_s,
        }


def _truncate(text: str | bytes | None) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    if len(text) <= MAX_OUTPUT:
        return text
    return text[:MAX_OUTPUT] + f"\n...[truncated {len(text) - MAX_OUTPUT} chars]"


def _run(
    code: str,
    filename: str,
    argv: list[str],
    timeout: int,
    workdir: str | Path | None,
    source_dir: str | Path | None,
) -> ExecResult:
    start = time.time()
    owned = workdir is None
    tmp = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="zurix-sandbox-"))
    tmp.mkdir(parents=True, exist_ok=True)
    script = tmp / filename
    script.write_text(code)

    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    python_path = [str(source_dir)] if source_dir else []
    if os.environ.get("PYTHONPATH"):
        python_path.append(os.environ["PYTHONPATH"])
    if python_path:
        env["PYTHONPATH"] = os.pathsep.join(python_path)

    try:
        proc = subprocess.run(
            argv,
            cwd=str(tmp),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            start_new_session=True,
        )
        return ExecResult(
            passed=proc.returncode == 0,
            exit_code=proc.returncode,
            stdout=_truncate(proc.stdout),
            stderr=_truncate(proc.stderr),
            duration_s=round(time.time() - start, 3),
        )
    except subprocess.TimeoutExpired as exc:
        return ExecResult(
            passed=False,
            exit_code=None,
            stdout=_truncate(exc.stdout),
            stderr=_truncate(exc.stderr) + f"\nTest exceeded {timeout}s timeout",
            timed_out=True,
            duration_s=round(time.time() - start, 3),
        )
    finally:
        if owned:
            shutil.rmtree(tmp, ignore_errors=True)


def run_python(
    code: str,
    timeout: int = DEFAULT_TIMEOUT,
    workdir: str | Path | None = None,
    source_dir: str | Path | None = None,
) -> ExecResult:
    """Execute Python test code with the current interpreter."""
    return _run(
        code,
        "test_micro_mock.py",
        [sys.executable, "test_micro_mock.py"],
        timeout,
        workdir,
        source_dir,
    )


def run_javascript(
    code: str,
    timeout: int = DEFAULT_TIMEOUT,
    workdir: str | Path | None = None,
    source_dir: str | Path | None = None,
) -> ExecResult:
    """Execute JavaScript test code with Node, if available."""
    node = shutil.which("node")
    if not node:
        return ExecResult(
            passed=False,
            exit_code=None,
            stdout="",
            stderr="node executable not found on PATH",
        )
    return _run(
        code,
        "micro_mock.test.js",
        [node, "micro_mock.test.js"],
        timeout,
        workdir,
        source_dir,
    )
