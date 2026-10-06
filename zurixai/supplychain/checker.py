"""Supply-Chain Checker — validates npm/PyPI packages against registry metadata."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

from zurixai.manifests import distribution_spellings, python_declared_deps, python_declared_specs


def check_supply_chain(project_dir: Path) -> dict:
    """Check dependencies for typosquatting, suspicious patterns, and registry metadata."""
    result: dict[str, Any] = {
        "checked": 0,
        "suspicious": 0,
        "unavailable": 0,
        "suspicious_packages": [],
        "version_not_found": [],
        "details": {},
    }

    # Collect packages from package.json + requirements.txt
    packages = _collect_packages(project_dir)
    specs = _collect_specs(project_dir)

    if not packages:
        return result

    # Check each package for local patterns first
    local_suspicious: dict[str, tuple[int, list[str]]] = {}
    for pkg_name in packages:
        suspicion_score = 0
        reasons: list[str] = []

        if _is_likely_typosquat(pkg_name):
            suspicion_score += 2
            reasons.append("possible typosquatting pattern")

        if _has_suspicious_name(pkg_name):
            suspicion_score += 1
            reasons.append("suspicious naming pattern")

        if suspicion_score > 0:
            local_suspicious[pkg_name] = (suspicion_score, reasons)

    # Concurrent registry checks
    registry_results = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {}
        for pkg_name, pkg_source in packages.items():
            if pkg_source == "npm":
                futures[executor.submit(_check_npm_registry, pkg_name)] = (pkg_name, "npm")
            elif pkg_source == "pypi":
                futures[executor.submit(_check_pypi_registry, pkg_name)] = (pkg_name, "pypi")

        for future in as_completed(futures):
            pkg_name, pkg_source = futures[future]
            try:
                info = future.result()
                registry_results[pkg_name] = info or {"status": "unavailable"}
            except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
                registry_results[pkg_name] = {"status": "unavailable"}

    # Combine local + registry results
    for pkg_name, pkg_source in packages.items():
        result["checked"] += 1
        suspicion_score = 0
        reasons = []

        # Local pattern checks
        if pkg_name in local_suspicious:
            score, local_reasons = local_suspicious[pkg_name]
            suspicion_score += score
            reasons.extend(local_reasons)

        # Registry checks
        if pkg_name in registry_results:
            info = registry_results[pkg_name]
            result["details"][pkg_name] = {k: v for k, v in info.items() if k not in ("versions", "yanked_versions")}
            if info.get("status") == "unavailable":
                result["unavailable"] += 1
            if info.get("status") == "not_found":
                suspicion_score += 3
                reasons.append("package not found in public registry")
            if info.get("is_deprecated"):
                suspicion_score += 2
                reasons.append("package is deprecated")
            if info.get("is_unmaintained"):
                suspicion_score += 1
                reasons.append("unmaintained (no recent updates)")

        info = registry_results.get(pkg_name, {})
        for spec in sorted(specs.get(pkg_name, ())):
            if info.get("status") == "ok" and not _spec_satisfied(
                    spec, info.get("versions", []), pkg_source, info.get("yanked_versions", [])):
                result["version_not_found"].append({
                    "name": pkg_name, "source": pkg_source, "spec": spec,
                    "latest_version": info.get("latest_version", ""),
                })

        if suspicion_score >= 2:
            result["suspicious"] += 1
            result["suspicious_packages"].append({
                "name": pkg_name,
                "source": pkg_source,
                "score": suspicion_score,
                "reasons": reasons,
            })

    return result


def classify_undeclared(npm_undeclared: dict, pypi_undeclared: dict) -> dict:
    """Look up undeclared imports in their registry.

    phantom    — the package does not exist in the registry (hallucinated)
    undeclared — it exists but is missing from the manifest
    unverified — the registry could not be reached
    """
    result: dict[str, list[dict]] = {"phantom": [], "undeclared": [], "unverified": []}
    lookups = [("npm", name, info) for name, info in npm_undeclared.items()]
    lookups += [("pypi", name, info) for name, info in pypi_undeclared.items()]
    if not lookups:
        return result

    def lookup(item: tuple[str, str, dict]) -> tuple[str, str]:
        source, name, info = item
        if source == "npm":
            return _check_npm_registry(info["package"])["status"], info["package"]
        status = _check_pypi_registry(info["package"])["status"]
        if status != "not_found":
            return status, info["package"]
        # Before calling it a phantom, try the usual alternate spellings (markdown_it → markdown-it-py).
        for alternate in distribution_spellings(name)[1:]:
            alt_status = _check_pypi_registry(alternate)["status"]
            if alt_status != "not_found":
                return alt_status, alternate
        return "not_found", info["package"]

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(lookup, lookups))

    bucket = {"not_found": "phantom", "ok": "undeclared"}
    for (source, name, info), (status, package) in zip(lookups, outcomes, strict=True):
        entry = {"name": name, "package": package, "source": source, "files": info["files"]}
        result[bucket.get(status, "unverified")].append(entry)
    return result


def _collect_packages(project_dir: Path) -> dict[str, str]:
    """Collect declared package names from package.json and the Python manifests."""
    packages: dict[str, str] = {}

    package_json = project_dir / "package.json"
    if package_json.exists():
        try:
            data = json.loads(package_json.read_text())
            for field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                for dep in data.get(field) or {}:
                    packages[dep] = "npm"
        except json.JSONDecodeError:
            pass

    for dep in python_declared_deps(project_dir):
        packages[dep] = "pypi"

    return packages


def _collect_specs(project_dir: Path) -> dict[str, set[str]]:
    """Declared version constraints: npm ranges from package.json, PEP 440 specifiers for Python."""
    specs: dict[str, set[str]] = {}
    package_json = project_dir / "package.json"
    if package_json.exists():
        try:
            data = json.loads(package_json.read_text())
            for field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                for dep, rng in (data.get(field) or {}).items():
                    if isinstance(rng, str) and _is_npm_range(rng):
                        specs.setdefault(dep, set()).add(rng.strip())
        except json.JSONDecodeError:
            pass
    for name, found in python_declared_specs(project_dir).items():
        specs.setdefault(name, set()).update(found)
    return specs


def _is_npm_range(rng: str) -> bool:
    """A semver range we can evaluate (not a URL, path, git/workspace/alias spec, or dist-tag)."""
    rng = rng.strip()
    if not rng or rng in ("*", "x", "latest") or ":" in rng or "/" in rng:
        return False
    return any(ch.isdigit() for ch in rng)


def _spec_satisfied(spec: str, versions: list[str], source: str, yanked: list[str] | None = None) -> bool:
    """Whether any published version satisfies the constraint. Unparseable constraints count as satisfied.

    PyPI: like pip (PEP 592), a yanked release satisfies only an exact `==`/`===` pin, never a range.
    """
    if source == "npm":
        import semantic_version

        try:
            npm_spec = semantic_version.NpmSpec(spec)
        except ValueError:
            return True
        for v in versions:
            try:
                if npm_spec.match(semantic_version.Version(v)):
                    return True
            except ValueError:
                continue
        return False

    from packaging.specifiers import InvalidSpecifier, SpecifierSet
    from packaging.version import InvalidVersion, Version

    try:
        spec_set = SpecifierSet(spec)
    except InvalidSpecifier:
        return True
    specs = list(spec_set)
    exact_pin = len(specs) == 1 and specs[0].operator in ("==", "===") and "*" not in specs[0].version
    candidates = list(versions) + (list(yanked or []) if exact_pin else [])
    parsed = []
    for v in candidates:
        try:
            parsed.append(Version(v))
        except InvalidVersion:
            continue
    return any(True for _ in spec_set.filter(parsed))


def _is_likely_typosquat(pkg_name: str) -> bool:
    """Check if a package name looks like a typosquatting attempt."""
    # Strip @scope/ prefix for pattern matching
    name = pkg_name.split("/")[-1] if "/" in pkg_name else pkg_name

    # Common typosquatting patterns
    suspicious_patterns = [
        r"^[a-z]{20,}$",  # Very long names (single segment)
        r"^[a-z]+_[a-z]+$",  # Underscored names (npm uses hyphens)
        r"^(test|debug|tmp|temp)-",  # Test/debug prefixes
    ]

    for pattern in suspicious_patterns:
        if re.match(pattern, name):
            return True

    # Check for character substitution (l→1, o→0, etc.) — skip @scope prefix
    # Only flag if ALL characters are leet speak (not just one at the end)
    leet_speak = {"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t"}
    normalized = name
    for char, replacement in leet_speak.items():
        normalized = normalized.replace(char, replacement)

    # Count how many characters were changed
    changes = sum(1 for a, b in zip(name, normalized) if a != b)
    # Only flag if multiple characters changed (single trailing number is common, e.g. urllib3)
    return changes > 1


def _has_suspicious_name(pkg_name: str) -> bool:
    """Check for suspicious naming patterns."""
    # Names that are very similar to popular packages
    popular_prefixes = ["lodash", "express", "react", "axios", "moment", "chalk"]
    for prefix in popular_prefixes:
        if pkg_name.startswith(prefix) and pkg_name != prefix and len(pkg_name) < len(prefix) + 5:
            return True
    return False


def _check_npm_registry(pkg_name: str) -> dict:
    """Check npm registry for package metadata."""
    try:
        resp = httpx.get(f"https://registry.npmjs.org/{pkg_name}", timeout=5.0)
        if resp.status_code == 404:
            return {"status": "not_found"}
        if resp.status_code == 200:
            data = resp.json()
            latest_version = data.get("dist-tags", {}).get("latest", "")
            time_data = data.get("time", {})
            modified = time_data.get("modified", "")
            deprecated = data.get("versions", {}).get(latest_version, {}).get("deprecated", None)

            # Check if unmaintained (no update in 2+ years)
            is_unmaintained = False
            if modified:
                from datetime import datetime
                try:
                    last_modified = datetime.fromisoformat(modified)
                    is_unmaintained = (datetime.now(last_modified.tzinfo) - last_modified).days > 730
                except (ValueError, TypeError):
                    pass

            return {
                "status": "ok",
                "latest_version": latest_version,
                "versions": list(data.get("versions", {})),
                "last_modified": modified,
                "is_deprecated": deprecated is not None,
                "is_unmaintained": is_unmaintained,
            }
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        pass
    return {"status": "unavailable"}


def _check_pypi_registry(pkg_name: str) -> dict:
    """Check PyPI registry for package metadata."""
    try:
        resp = httpx.get(f"https://pypi.org/pypi/{pkg_name}/json", timeout=5.0)
        if resp.status_code == 404:
            return {"status": "not_found"}
        if resp.status_code == 200:
            data = resp.json()
            info = data.get("info", {})
            release = data.get("releases", {})
            latest_version = info.get("version", "")

            # Get last release date
            last_release_date = None
            if latest_version and latest_version in release:
                files = release[latest_version]
                if files:
                    last_release_date = files[0].get("upload_time_iso_8601", "")

            # Check if unmaintained
            is_unmaintained = False
            if last_release_date:
                from datetime import datetime
                try:
                    last_date = datetime.fromisoformat(last_release_date)
                    is_unmaintained = (datetime.now(last_date.tzinfo) - last_date).days > 730
                except (ValueError, TypeError):
                    pass

            return {
                "status": "ok",
                "latest_version": latest_version,
                # pip skips yanked releases for ranges but installs them for an exact pin (PEP 592).
                "versions": [v for v, files in release.items()
                             if files and not all(f.get("yanked") for f in files)],
                "yanked_versions": [v for v, files in release.items()
                                    if files and all(f.get("yanked") for f in files)],
                "last_release": last_release_date,
                "is_deprecated": info.get("yanked", False),
                "is_unmaintained": is_unmaintained,
            }
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        pass
    return {"status": "unavailable"}
