"""AST Import Validator for PyPI packages."""

from __future__ import annotations

import ast
import re
from pathlib import Path


def validate_pypi_imports(project_dir: Path) -> dict:
    """Scan Python files for imports and validate against pyproject.toml + requirements.txt."""
    result = {"valid": 0, "invalid": 0, "invalid_imports": [], "checked_files": 0}

    # Collect declared dependencies from pyproject.toml + requirements.txt
    declared_deps = _get_declared_deps(project_dir)

    # Detect project name (for self-import filtering)
    project_name = _get_project_name(project_dir)
    if project_name:
        declared_deps.add(project_name.lower())

    # Find Python files
    py_files: set[Path] = set()
    for f in project_dir.glob("**/*.py"):
        if "__pycache__" in str(f) or ".zurix" in str(f) or "node_modules" in str(f):
            continue
        py_files.add(f)

    # Standard library modules (Python 3.10+)
    STDLIB = {
        # Builtins
        "__future__", "abc", "aifc", "argparse", "array", "ast", "asynchat",
        "asyncio", "asyncore", "atexit", "audioop",
        # B
        "base64", "bdb", "binascii", "binhex", "bisect", "builtins",
        # C
        "calendar", "cgi", "cgitb", "chunk", "cmath", "cmd", "code", "codecs",
        "codeop", "collections", "colorsys", "compileall", "concurrent",
        "configparser", "contextlib", "contextvars", "copy", "copyreg",
        "cProfile", "crypt", "csv", "ctypes", "curses",
        # D
        "dataclasses", "datetime", "dbm", "decimal", "difflib", "dis",
        "distutils", "doctest",
        # E
        "email", "encodings", "enum", "errno", "faulthandler", "fcntl",
        "filecmp", "fileinput", "fnmatch", "fractions", "ftplib",
        # F
        "functools",
        # G
        "gc", "getopt", "getpass", "gettext", "glob", "grp", "gzip",
        # H
        "hashlib", "heapq", "hmac", "html", "http", "imaplib", "imghdr",
        "imp", "importlib", "inspect", "io", "ipaddress", "itertools",
        # J
        "json",
        # K
        "keyword",
        # L
        "lib2to3", "linecache", "locale", "logging", "lzma",
        # M
        "mailbox", "mailcap", "marshal", "math", "mimetypes", "mmap",
        "modulefinder", "multiprocessing",
        # N
        "netrc", "nis", "nntplib", "numbers",
        # O
        "operator", "optparse", "os", "ossaudiodev",
        # P
        "pathlib", "pdb", "pickle", "pickletools", "pipes", "pkgutil",
        "platform", "plistlib", "poplib", "posix", "posixpath", "pprint",
        "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr",
        "pydoc", "queue",
        # Q-R
        "quopri",
        # S
        "random", "re", "readline", "reprlib", "resource", "rlcompleter",
        "runpy",
        # T
        "sched", "secrets", "select", "selectors", "shelve", "shlex",
        "shutil", "signal", "site", "smtpd", "smtplib", "sndhdr",
        "socket", "socketserver", "sqlite3", "ssl", "stat", "statistics",
        "string", "stringprep", "struct", "subprocess", "sunau", "symtable",
        "sys", "sysconfig", "syslog",
        # T
        "tabnanny", "tarfile", "telnetlib", "tempfile", "termios", "test",
        "textwrap", "threading", "time", "timeit", "tkinter", "token",
        "tokenize", "tomllib", "trace", "traceback", "tracemalloc", "tty",
        "turtle", "types", "typing",
        # U
        "unicodedata", "unittest", "urllib",
        # V
        "uuid", "venv",
        # W
        "warnings", "wave", "weakref", "webbrowser", "winreg", "winsound",
        "wsgiref", "xdrlib",
        # X-Z
        "xml", "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib",
        # Commonly confused with third-party
        "_thread", "_io", "_collections_abc",
    }

    # Package name mapping (import name → PyPI name)
    import_to_pypi = {
        "PIL": "pillow",
        "cv2": "opencv-python",
        "sklearn": "scikit-learn",
        "yaml": "pyyaml",
        "attr": "attrs",
        "bs4": "beautifulsoup4",
        "dateutil": "python-dateutil",
        "jinja2": "jinja2",
        "jwt": "PyJWT",
        "magic": "python-magic",
        "numpy": "numpy",
        "pandas": "pandas",
        "requests": "requests",
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "pydantic": "pydantic",
        "httpx": "httpx",
        "pytest": "pytest",
        "typing_extensions": "typing-extensions",
    }

    for f in py_files:
        result["checked_files"] += 1
        try:
            tree = ast.parse(f.read_text(errors="ignore"))
        except (SyntaxError, ValueError):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root.startswith("_"):
                        continue
                    _accumulate(result, _check_import(root, declared_deps, STDLIB, import_to_pypi, f))

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    # Skip relative imports (from .module import ...)
                    if node.level > 0:
                        continue
                    root = node.module.split(".")[0]
                    if root.startswith("_"):
                        continue
                    _accumulate(result, _check_import(root, declared_deps, STDLIB, import_to_pypi, f))

    return result


def _accumulate(result: dict, check: dict) -> None:
    """Increment counters instead of replacing."""
    result["valid"] += check.get("valid", 0)
    result["invalid"] += check.get("invalid", 0)
    result["invalid_imports"].extend(check.get("invalid_imports", []))


def _check_import(
    root: str,
    declared_deps: set[str],
    stdlib_modules: set[str],
    import_to_pypi: dict[str, str],
    file_path: Path,
) -> dict:
    """Check a single import root against declared deps."""
    if root in stdlib_modules or root.startswith("_"):
        return {"valid": 0, "invalid": 0, "invalid_imports": []}

    # Try to match import name to PyPI package
    pypi_name = import_to_pypi.get(root, root.lower().replace("_", "-"))

    if root in declared_deps or pypi_name in declared_deps:
        return {"valid": 1, "invalid": 0, "invalid_imports": []}

    return {
        "valid": 0,
        "invalid": 1,
        "invalid_imports": [f"{root} (from {file_path.name})"],
    }


def _get_declared_deps(project_dir: Path) -> set[str]:
    """Extract dependency names from pyproject.toml and requirements.txt."""
    deps: set[str] = set()

    # pyproject.toml
    pyproject = project_dir / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text()
        for match in re.finditer(r'"([a-zA-Z0-9_-]+)(?:\[.*?\])?(?:>=.*?|<.*?|~=.*?|!=.*?|==.*?)"', content):
            deps.add(match.group(1).lower().replace("_", "-"))

    # requirements.txt
    req_file = project_dir / "requirements.txt"
    if req_file.exists():
        for line in req_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                pkg_name = re.split(r"[>=<~!]", line)[0].strip()
                deps.add(pkg_name.lower().replace("_", "-"))

    return deps


def _get_project_name(project_dir: Path) -> str | None:
    """Extract project name from pyproject.toml or setup.py."""
    pyproject = project_dir / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text()
        match = re.search(r'^name\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
        if match:
            return match.group(1)

    setup_py = project_dir / "setup.py"
    if setup_py.exists():
        content = setup_py.read_text()
        match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)

    return None
