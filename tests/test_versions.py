"""Declared versions that don't exist on the registry (pinned/ranged deps that can't install)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from zurixai.cli.check import count_critical, run_checks
from zurixai.supplychain.checker import _spec_satisfied, check_supply_chain

PYPI = {
    "openpyxl": {"3.0.10": [{"yanked": False}], "3.1.5": [{"yanked": False}], "3.1.4": [{"yanked": True}],
                 "3.2.0b1": [{"yanked": False}], "9.9.9": []},
    "requests": {"2.32.3": [{"yanked": False}]},
}
PYPI_LATEST = {"openpyxl": "3.1.5", "requests": "2.32.3"}
NPM = {"airtable": ["0.11.6", "0.12.2"], "dbf": ["0.1.0", "0.2.0"], "express": ["4.21.2", "5.0.0"]}


def _registry(url: str, **_: object) -> httpx.Response:
    if url.startswith("https://pypi.org/pypi/"):
        name = url.split("/")[4]
        if name not in PYPI:
            return httpx.Response(404)
        return httpx.Response(200, json={"info": {"version": PYPI_LATEST[name]}, "releases": PYPI[name]})
    name = url.removeprefix("https://registry.npmjs.org/")
    if name not in NPM:
        return httpx.Response(404)
    return httpx.Response(200, json={"dist-tags": {"latest": NPM[name][-1]},
                                     "versions": {v: {} for v in NPM[name]}, "time": {}})


def _scan(tmp_path: Path, requirements: str = "", package_json: dict | None = None) -> dict:
    if requirements:
        (tmp_path / "requirements.txt").write_text(requirements)
    if package_json is not None:
        (tmp_path / "package.json").write_text(json.dumps(package_json))
    with patch("zurixai.supplychain.checker.httpx.get", side_effect=_registry):
        return check_supply_chain(tmp_path)


def _missing(result: dict) -> list[tuple[str, str]]:
    return sorted((e["name"], e["spec"]) for e in result["version_not_found"])


def test_python_pins_and_ranges_that_no_release_satisfies(tmp_path: Path) -> None:
    result = _scan(tmp_path, "openpyxl>=3.6.0\nrequests==2.32.3\n")
    assert _missing(result) == [("openpyxl", ">=3.6.0")]
    assert result["version_not_found"][0]["latest_version"] == "3.1.5"
    assert result["suspicious"] == 0


@pytest.mark.parametrize(("spec", "ok"), [
    ("==3.1.5", True), (">=3.0,<3.2", True), ("~=3.1.0", True), ("==3.1.*", True),
    ("==3.10.10", False), (">=3.6.0", False),
    ("==3.1.4", False),   # only yanked files
    ("==9.9.9", False),   # release entry with no files
    ("==3.2.0b1", True),  # an explicitly pinned pre-release exists
])
def test_python_specifier_rules(spec: str, ok: bool) -> None:
    versions = [v for v, files in PYPI["openpyxl"].items() if files and not all(f["yanked"] for f in files)]
    assert _spec_satisfied(spec, versions, "pypi") is ok


@pytest.mark.parametrize(("rng", "ok"), [
    ("^0.12.0", True), ("~0.11.0", True), ("0.12.2", True), (">=0.11 <1", True), ("1.x || ^0.12.0", True),
    ("^2.1.0", False), ("^1.1.0", False), ("0.13.0", False),
])
def test_npm_range_rules(rng: str, ok: bool) -> None:
    assert _spec_satisfied(rng, NPM["airtable"], "npm") is ok


def test_npm_ranges_that_no_release_satisfies(tmp_path: Path) -> None:
    result = _scan(tmp_path, package_json={"dependencies": {"airtable": "^2.1.0", "dbf": "^0.1.0",
                                                            "express": "^4.18.0"}})
    assert _missing(result) == [("airtable", "^2.1.0")]


def test_non_semver_npm_specs_are_not_judged(tmp_path: Path) -> None:
    result = _scan(tmp_path, package_json={"dependencies": {
        "airtable": "latest", "dbf": "file:../dbf", "express": "github:expressjs/express"}})
    assert result["version_not_found"] == []


def test_unpinned_and_missing_packages_are_not_version_findings(tmp_path: Path) -> None:
    result = _scan(tmp_path, "requests\nnot-a-real-pkg-zx==1.0\n")
    assert result["version_not_found"] == []
    assert result["details"]["not-a-real-pkg-zx"]["status"] == "not_found"
    assert "versions" not in result["details"]["requests"]


def test_missing_version_is_critical_and_fails_the_check(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("openpyxl>=3.6.0\n")
    (tmp_path / "main.py").write_text("import openpyxl\n")
    with patch("zurixai.supplychain.checker.httpx.get", side_effect=_registry):
        checks = run_checks(tmp_path, ".zurix/rules.md")
    assert count_critical(checks) == 1
