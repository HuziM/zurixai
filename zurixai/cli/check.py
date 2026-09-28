"""zurix check — run all checks on a project directory."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from zurixai.ast.npm_validator import validate_npm_imports
from zurixai.ast.pypi_validator import validate_pypi_imports
from zurixai.config import Config
from zurixai.drift.sentinel import check_drift
from zurixai.rules.parser import parse_rules
from zurixai.supplychain.checker import check_supply_chain, classify_undeclared

CRITICAL_SUPPLY_SCORE = 3


class _C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    DIM = "\033[2m"

    @classmethod
    def disable(cls):
        for attr in ("RESET", "BOLD", "RED", "GREEN", "YELLOW", "BLUE", "CYAN", "DIM"):
            setattr(cls, attr, "")


def run_checks(project_dir: Path, rules_file: str) -> dict:
    """Run every check on project_dir and return the combined results."""
    npm = validate_npm_imports(project_dir)
    pypi = validate_pypi_imports(project_dir)
    return {
        "npm_imports": npm,
        "pypi_imports": pypi,
        "imports": classify_undeclared(npm["undeclared"], pypi["undeclared"]),
        "supply_chain": check_supply_chain(project_dir),
        "drift": check_drift(project_dir),
        "rules": parse_rules(project_dir / rules_file),
    }


def count_critical(checks: dict) -> int:
    invalid: int = checks.get("npm_imports", {}).get("invalid", 0) + checks.get("pypi_imports", {}).get("invalid", 0)
    suspicious = sum(
        1 for pkg in checks.get("supply_chain", {}).get("suspicious_packages", [])
        if pkg.get("score", 0) >= CRITICAL_SUPPLY_SCORE
    )
    return invalid + suspicious


def cmd_check(cfg: Config, path: str, *, use_json: bool, list_checks: bool, no_color: bool) -> int:
    """Run checks and print results. Returns the process exit code."""
    if no_color or not sys.stdout.isatty():
        _C.disable()
    if list_checks:
        _print_check_list()
        return 0

    project_dir = Path(path).resolve()
    if not project_dir.is_dir():
        print(f"zurix check: not a directory: {path}", file=sys.stderr)
        return 2

    start = time.time()
    checks = run_checks(project_dir, cfg.rules_file)
    elapsed = time.time() - start
    results = {"project": str(project_dir), "checks": checks, "scan_time_seconds": round(elapsed, 2)}

    if use_json:
        print(json.dumps(results, indent=2, default=str))
    else:
        _print_results(results, elapsed)
    return 1 if count_critical(checks) else 0


def _install_hint(entry: dict) -> str:
    return f"npm install {entry['package']}" if entry["source"] == "npm" else f"pip install {entry['package']}"


def _print_imports(checks: dict, issues: list[tuple[str, str]]) -> None:
    npm = checks.get("npm_imports", {})
    pypi = checks.get("pypi_imports", {})
    valid = npm.get("valid", 0) + pypi.get("valid", 0)
    invalid = npm.get("invalid", 0) + pypi.get("invalid", 0)
    imports = checks.get("imports", {"phantom": [], "undeclared": [], "unverified": []})

    if invalid == 0:
        print(f"\n  {_C.GREEN}✓{_C.RESET} Imports: {_C.GREEN}{valid}/{valid} declared{_C.RESET}")
        return

    print(f"\n  {_C.RED}✗{_C.RESET} Imports: {_C.RED}{invalid} not declared{_C.RESET} ({valid}/{valid + invalid} declared)")
    for entry in imports["phantom"]:
        files = ", ".join(entry["files"][:3])
        issues.append(("critical", f"Phantom import: {entry['name']}"))
        print(f"    {_C.RED}•{_C.RESET} {_C.RED}CRITICAL{_C.RESET} phantom: {entry['name']} "
              f"— {entry['package']} not found on {entry['source']} ({files})")
        print(f"      {_C.DIM}Fix: remove it or replace it with a package that exists{_C.RESET}")
    for entry in imports["undeclared"]:
        files = ", ".join(entry["files"][:3])
        issues.append(("critical", f"Missing dependency: {entry['name']}"))
        print(f"    {_C.RED}•{_C.RESET} {_C.RED}CRITICAL{_C.RESET} missing dependency: {entry['name']} ({files})")
        print(f"      {_C.DIM}Fix: {_install_hint(entry)} and add it to your manifest{_C.RESET}")
    for entry in imports["unverified"]:
        issues.append(("warning", f"Unverified import: {entry['name']}"))
        print(f"    {_C.YELLOW}•{_C.RESET} {_C.YELLOW}WARNING{_C.RESET} {entry['name']}: "
              f"not declared, registry unreachable — could not tell if it exists")


def _print_results(results: dict, elapsed: float) -> None:
    """Pretty-print check results to terminal with colors and severity."""
    checks = results["checks"]
    issues: list[tuple[str, str]] = []

    print()
    print(f"{_C.BOLD}{'═' * 56}{_C.RESET}")
    print(f"{_C.BOLD}  ZurixAI Check Results{_C.RESET}")
    print(f"{_C.BOLD}{'═' * 56}{_C.RESET}")

    _print_imports(checks, issues)

    # --- Supply Chain ---
    supply = checks.get("supply_chain", {})
    suspicious = supply.get("suspicious", 0)
    unavailable = supply.get("unavailable", 0)
    if unavailable:
        message = f"{unavailable} registry lookup(s) unavailable; scan incomplete"
        issues.append(("warning", message))
        print(f"  Supply Chain: {message}")
    if suspicious == 0 and not unavailable:
        print(f"  {_C.GREEN}✓{_C.RESET} Supply Chain: {_C.GREEN}{supply.get('checked', 0)} packages OK{_C.RESET}")
    elif suspicious:
        print(f"  {_C.YELLOW}!{_C.RESET} Supply Chain: {_C.YELLOW}{suspicious} suspicious{_C.RESET} ({supply.get('checked', 0)} checked)")
        for pkg in supply.get("suspicious_packages", []):
            severity = "critical" if pkg.get("score", 0) >= CRITICAL_SUPPLY_SCORE else "warning"
            issues.append((severity, f"Suspicious package: {pkg['name']} ({', '.join(pkg.get('reasons', []))})"))
            color = _C.YELLOW if severity == "warning" else _C.RED
            label = "WARNING" if severity == "warning" else "CRITICAL"
            print(f"    {_C.YELLOW}•{_C.RESET} {color}{label}{_C.RESET} {pkg['name']}: {', '.join(pkg.get('reasons', []))}")
            print(f"      {_C.DIM}Fix: Review package, consider alternatives{_C.RESET}")

    # --- Drift ---
    drift = checks.get("drift", {})
    orphaned = drift.get("orphaned_functions", 0)
    stale = drift.get("stale_files", 0)
    if orphaned == 0 and stale == 0:
        print(f"  {_C.GREEN}✓{_C.RESET} Drift: {_C.GREEN}No orphaned functions or stale files{_C.RESET}")
    else:
        if orphaned > 0:
            print(f"  {_C.YELLOW}!{_C.RESET} Drift: {_C.YELLOW}{orphaned} orphaned functions{_C.RESET}")
            for fn in drift.get("orphaned_list", [])[:5]:
                issues.append(("info", f"Orphaned: {fn}"))
                print(f"    {_C.DIM}• {fn}{_C.RESET}")
            if orphaned > 5:
                print(f"    {_C.DIM}... and {orphaned - 5} more{_C.RESET}")
        if stale > 0:
            print(f"  {_C.YELLOW}!{_C.RESET} Drift: {_C.YELLOW}{stale} stale files{_C.RESET} (>30 days)")
            for sf in drift.get("stale_list", [])[:5]:
                issues.append(("info", f"Stale: {sf['file']} ({sf['days_since_modified']}d)"))
                print(f"    {_C.DIM}• {sf['file']} ({sf['days_since_modified']}d){_C.RESET}")

    # --- Rules ---
    rules = checks.get("rules", {})
    rule_count = rules.get("rule_count", 0)
    if rule_count > 0:
        sections = rules.get("sections", [])
        print(f"  {_C.CYAN}i{_C.RESET} Rules: {_C.CYAN}{rule_count} rules loaded{_C.RESET} ({', '.join(sections)})")
    else:
        print(f"  {_C.DIM}○ Rules: No .zurix/rules.md found{_C.RESET}")

    # --- Summary ---
    critical = sum(1 for s, _ in issues if s == "critical")
    warnings = sum(1 for s, _ in issues if s == "warning")
    info = sum(1 for s, _ in issues if s == "info")

    print(f"\n{_C.BOLD}{'─' * 56}{_C.RESET}")
    if critical + warnings + info == 0:
        print(f"  {_C.GREEN}{_C.BOLD}All checks passed{_C.RESET} {_C.DIM}({elapsed:.1f}s){_C.RESET}")
    else:
        parts = []
        if critical:
            parts.append(f"{_C.RED}{critical} critical{_C.RESET}")
        if warnings:
            parts.append(f"{_C.YELLOW}{warnings} warning{_C.RESET}")
        if info:
            parts.append(f"{_C.BLUE}{info} info{_C.RESET}")
        print(f"  {_C.BOLD}Summary:{_C.RESET} {', '.join(parts)} {_C.DIM}({elapsed:.1f}s){_C.RESET}")
    print(f"{'═' * 56}\n")


def _print_check_list() -> None:
    """List all available check types."""
    checks = [
        ("npm_imports", "JS/TS imports vs package.json"),
        ("pypi_imports", "Python imports vs pyproject.toml / requirements / setup.py"),
        ("imports", "Undeclared imports looked up on npm/PyPI: phantom vs missing"),
        ("supply_chain", "Declared dependencies: registry status, typosquatting"),
        ("drift", "Orphaned functions and stale files"),
        ("rules", "Custom rules from .zurix/rules.md (loaded, not enforced yet)"),
    ]
    print()
    print(f"{_C.BOLD}Available check types:{_C.RESET}")
    print()
    for name, desc in checks:
        print(f"  {_C.GREEN}{name}{_C.RESET}")
        print(f"    {_C.DIM}{desc}{_C.RESET}")
    print()
