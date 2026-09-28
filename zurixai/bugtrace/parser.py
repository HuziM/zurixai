"""Stack trace parser for Python tracebacks, JS errors and Sentry-style output."""

from __future__ import annotations

import re

# Python traceback patterns
_PY_HEADER = re.compile(
    r"Traceback \(most recent call last\):", re.MULTILINE
)
_PY_FRAME = re.compile(
    r'^\s+File "(?P<file>[^"]+)", line (?P<line>\d+)(?:, in (?P<func>\S+))?\n'
    r"(?:\s+(?P<context>.+)\n)?",
    re.MULTILINE,
)
_PY_ERROR = re.compile(
    r"^(?P<type>\S*(?:Error|Exception|Warning))\s*(?::\s*(?P<message>.+))?$",
    re.MULTILINE,
)

# JavaScript / Node stack trace patterns
_JS_FRAME = re.compile(
    r"^\s+at\s+(?:(?P<func>[^\s]+)\s+\()?(?P<file>[^():]+):(?P<line>\d+):(?P<col>\d+)\)?\s*$",
    re.MULTILINE,
)
_JS_ERROR = re.compile(
    r"^(?:(?P<type>\w*Error)\s*:\s*)?(?P<message>.+)$", re.MULTILINE
)

# Sentry-style (exception type + value + frames)
_SENTRY_HEADER = re.compile(
    r"^(?P<type>\S+)(?:\s*:\s*(?P<message>.+))?$", re.MULTILINE
)


class ParsedFrame:
    """A single stack frame."""

    __slots__ = ("column", "context", "file", "function", "line")

    def __init__(
        self,
        file: str,
        line: int,
        function: str = "",
        context: str = "",
        column: int | None = None,
    ) -> None:
        self.file = file
        self.line = line
        self.function = function
        self.context = context
        self.column = column

    def as_dict(self) -> dict:
        d: dict = {
            "file": self.file,
            "line": self.line,
            "function": self.function,
            "context": self.context,
        }
        if self.column is not None:
            d["column"] = self.column
        return d


class ParsedTrace:
    """Structured representation of a parsed stack trace."""

    __slots__ = ("error_message", "error_type", "frames", "language", "raw")

    def __init__(
        self,
        error_type: str,
        error_message: str,
        frames: list[ParsedFrame],
        language: str,
        raw: str,
    ) -> None:
        self.error_type = error_type
        self.error_message = error_message
        self.frames = frames
        self.language = language
        self.raw = raw

    @property
    def culprit(self) -> ParsedFrame | None:
        """The first non-library frame (most relevant to user code)."""
        for frame in self.frames:
            f = frame.file.lower()
            if not any(
                skip in f
                for skip in ("site-packages", "node_modules", "lib/python", "internal/")
            ):
                return frame
        return self.frames[0] if self.frames else None

    def as_dict(self) -> dict:
        culprit = self.culprit
        return {
            "error_type": self.error_type,
            "error_message": self.error_message,
            "frames": [f.as_dict() for f in self.frames],
            "culprit": culprit.as_dict() if culprit else None,
            "language": self.language,
        }


def _parse_python_traceback(raw: str) -> ParsedTrace | None:
    """Parse a standard Python traceback."""
    if not _PY_HEADER.search(raw):
        return None

    frames: list[ParsedFrame] = []
    for m in _PY_FRAME.finditer(raw):
        frames.append(
            ParsedFrame(
                file=m.group("file"),
                line=int(m.group("line")),
                function=m.group("func") or "",
                context=(m.group("context") or "").strip(),
            )
        )

    error_match = _PY_ERROR.search(raw)
    error_type = error_match.group("type") if error_match else "UnknownError"
    error_message = (error_match.group("message") or "").strip() if error_match else ""

    return ParsedTrace(
        error_type=error_type,
        error_message=error_message,
        frames=frames,
        language="python",
        raw=raw,
    )


def _parse_js_traceback(raw: str) -> ParsedTrace | None:
    """Parse a JavaScript / Node stack trace."""
    frames = []
    for m in _JS_FRAME.finditer(raw):
        frames.append(
            ParsedFrame(
                file=m.group("file"),
                line=int(m.group("line")),
                function=m.group("func") or "",
                column=int(m.group("col")) if m.group("col") else None,
            )
        )

    if not frames:
        return None

    error_type = ""
    error_message = ""
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("at "):
            continue
        err = _JS_ERROR.match(line)
        if err:
            error_type = err.group("type") or ""
            error_message = (err.group("message") or "").strip()
            break

    return ParsedTrace(
        error_type=error_type or "Error",
        error_message=error_message,
        frames=frames,
        language="javascript",
        raw=raw,
    )


def _parse_sentry_traceback(raw: str) -> ParsedTrace | None:
    """Parse a Sentry-style exception with ``ExceptionType: message`` header."""
    lines = [l for l in raw.splitlines() if l.strip()]
    if not lines:
        return None

    m = _SENTRY_HEADER.match(lines[0])
    if not m or not m.group("type"):
        return None

    error_type = m.group("type")
    if error_type.startswith("Traceback"):
        return None

    error_message = (m.group("message") or "").strip()
    js_frames = list(_JS_FRAME.finditer(raw))
    py_frames = list(_PY_FRAME.finditer(raw))

    frames: list[ParsedFrame] = []
    language = "unknown"
    if js_frames:
        language = "javascript"
        for fm in js_frames:
            frames.append(
                ParsedFrame(
                    file=fm.group("file"),
                    line=int(fm.group("line")),
                    function=fm.group("func") or "",
                    column=int(fm.group("col")) if fm.group("col") else None,
                )
            )
    elif py_frames:
        language = "python"
        for fm in py_frames:
            frames.append(
                ParsedFrame(
                    file=fm.group("file"),
                    line=int(fm.group("line")),
                    function=fm.group("func") or "",
                    context=(fm.group("context") or "").strip(),
                )
            )

    return ParsedTrace(
        error_type=error_type,
        error_message=error_message,
        frames=frames,
        language=language,
        raw=raw,
    )


def parse_trace(raw: str) -> ParsedTrace:
    """Parse a stack trace, auto-detecting format."""
    if not raw or not raw.strip():
        raise ValueError("empty stack trace")

    trace = _parse_python_traceback(raw)
    if trace is not None:
        return trace

    trace = _parse_sentry_traceback(raw)
    if trace is not None:
        return trace

    trace = _parse_js_traceback(raw)
    if trace is not None:
        return trace

    raise ValueError("unable to parse stack trace (unsupported format)")
