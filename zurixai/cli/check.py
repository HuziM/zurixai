"""zurix check — Run local quality checks on the current project."""

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
from zurixai.supplychain.checker import check_supply_chain


# ANSI color codes
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


def cmd_check(cfg: Config, args: list[str]) -> None:
    """Run free local checks, then optionally call engine for Pro features."""
    project_dir = Path.cwd()
    use_json = "--json" in args
    pro_mode = "--pro" in args
    use_color = "--no-color" not in args and sys.stdout.isatty()

    if not use_color:
        _C.disable()

    start_time = time.time()

    results: dict[str, object] = {
        "project": str(project_dir),
        "checks": {},
        "pro": pro_mode,
    }

    # --- 1. AST Import Validation ---
    npm_result = validate_npm_imports(project_dir)
    pypi_result = validate_pypi_imports(project_dir)
    results["checks"]["npm_imports"] = npm_result
    results["checks"]["pypi_imports"] = pypi_result

    # --- 2. Supply-Chain Check ---
    supply_result = check_supply_chain(project_dir)
    results["checks"]["supply_chain"] = supply_result

    # --- 3. Drift Sentinel ---
    drift_result = check_drift(project_dir)
    results["checks"]["drift"] = drift_result

    # --- 4. Rules Enforcement ---
    rules_file = project_dir / cfg.rules_file
    rules_result = parse_rules(rules_file)
    results["checks"]["rules"] = rules_result

    elapsed = time.time() - start_time
    results["scan_time_seconds"] = round(elapsed, 2)

    # --- Output ---
    if use_json:
        print(json.dumps(results, indent=2, default=str))
    else:
        _print_results(results, pro_mode, elapsed)


def _print_results(results: dict, pro_mode: bool, elapsed: float) -> None:
    """Pretty-print check results to terminal with colors and severity."""
    checks = results["checks"]
    issues = []  # collect all issues for summary

    print()
    print(f"{_C.BOLD}{'═' * 56}{_C.RESET}")
    print(f"{_C.BOLD}  ZurixAI Check Results{_C.RESET}")
    print(f"{_C.BOLD}{'═' * 56}{_C.RESET}")

    # --- AST Imports ---
    npm = checks.get("npm_imports", {})
    pypi = checks.get("pypi_imports", {})
    npm_valid = npm.get("valid", 0)
    npm_invalid = npm.get("invalid", 0)
    pypi_valid = pypi.get("valid", 0)
    pypi_invalid = pypi.get("invalid", 0)
    total_imports = npm_valid + pypi_valid + npm_invalid + pypi_invalid

    if npm_invalid + pypi_invalid == 0:
        print(f"\n  {_C.GREEN}✓{_C.RESET} Imports: {_C.GREEN}{npm_valid + pypi_valid}/{total_imports} valid{_C.RESET}")
    else:
        print(f"\n  {_C.RED}✗{_C.RESET} Imports: {_C.RED}{npm_invalid + pypi_invalid} invalid{_C.RESET} ({npm_valid + pypi_valid}/{total_imports} valid)")
        for imp in npm.get("invalid_imports", []):
            issues.append(("critical", f"Missing npm dependency: {imp}"))
            print(f"    {_C.RED}•{_C.RESET} {_C.RED}CRITICAL{_C.RESET} Missing npm dependency: {imp}")
            print(f"      {_C.DIM}Fix: npm install {imp.split(' (')[0]}{_C.RESET}")
        for imp in pypi.get("invalid_imports", []):
            issues.append(("critical", f"Missing PyPI dependency: {imp}"))
            print(f"    {_C.RED}•{_C.RESET} {_C.RED}CRITICAL{_C.RESET} Missing PyPI dependency: {imp}")
            print(f"      {_C.DIM}Fix: pip install {imp.split(' (')[0]}{_C.RESET}")

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
            severity = "warning" if pkg.get("score", 0) < 3 else "critical"
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

    # --- Pro upsell ---
    if not pro_mode:
        print(f"\n  {_C.DIM}Run 'zurix check --pro' for LLM-powered patches{_C.RESET}")
    else:
        print(f"\n  {_C.DIM}Pro mode: Connect engine for LLM-powered fixes{_C.RESET}")

    print(f"{'═' * 56}\n")
