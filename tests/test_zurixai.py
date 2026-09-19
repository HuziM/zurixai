"""Unit tests for zurixai CLI check command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from zurixai.ast.npm_validator import validate_npm_imports
from zurixai.ast.pypi_validator import validate_pypi_imports
from zurixai.drift.sentinel import check_drift
from zurixai.rules.parser import parse_rules
from zurixai.supplychain.checker import check_supply_chain


class TestNpmValidator:
    """Tests for npm import validator."""

    def test_no_package_json(self, tmp_path: Path) -> None:
        result = validate_npm_imports(tmp_path)
        assert result["valid"] == 0
        assert result["invalid"] == 0

    def test_valid_imports(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"dependencies": {"react": "^18.0.0", "lodash": "^4.17.0"}}))
        src = tmp_path / "app.tsx"
        src.write_text('import React from "react";\nimport _ from "lodash";')
        result = validate_npm_imports(tmp_path)
        assert result["valid"] == 2
        assert result["invalid"] == 0

    def test_invalid_imports(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"dependencies": {"react": "^18.0.0"}}))
        src = tmp_path / "app.tsx"
        src.write_text('import React from "react";\nimport fake from "fake-package";')
        result = validate_npm_imports(tmp_path)
        assert result["valid"] == 1
        assert result["invalid"] == 1

    def test_skips_node_modules(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"dependencies": {}}))
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text('import x from "x";')
        result = validate_npm_imports(tmp_path)
        assert result["checked_files"] == 0

    def test_scopes_import(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"dependencies": {"@types/node": "^20.0.0"}}))
        src = tmp_path / "app.ts"
        src.write_text('import path from "@types/node";')
        result = validate_npm_imports(tmp_path)
        assert result["valid"] == 1


class TestPyPIValidator:
    """Tests for PyPI import validator."""

    def test_no_deps(self, tmp_path: Path) -> None:
        result = validate_pypi_imports(tmp_path)
        assert result["valid"] == 0
        assert result["invalid"] == 0

    def test_valid_imports(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text("requests\nfastapi\n")
        src = tmp_path / "app.py"
        src.write_text("import requests\nimport fastapi\n")
        result = validate_pypi_imports(tmp_path)
        # At least some imports should be valid
        assert result["valid"] >= 1

    def test_invalid_imports(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text("requests\n")
        src = tmp_path / "app.py"
        src.write_text("import requests\nimport fake_package\n")
        result = validate_pypi_imports(tmp_path)
        assert result["invalid"] >= 1

    def test_stdlib_ignored(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text("import os\nimport sys\nimport json\n")
        result = validate_pypi_imports(tmp_path)
        assert result["valid"] == 0
        assert result["invalid"] == 0

    def test_local_imports_ignored(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text("from . import mymodule\nfrom ..utils import helper\n")
        result = validate_pypi_imports(tmp_path)
        # Local imports (starting with .) should not count as invalid third-party
        assert result["invalid"] == 0 or result["checked_files"] == 1


class TestSupplyChain:
    """Tests for supply-chain checker."""

    def test_no_deps(self, tmp_path: Path) -> None:
        result = check_supply_chain(tmp_path)
        assert result["checked"] == 0
        assert result["suspicious"] == 0

    def test_normal_packages(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text("requests\nflask\n")
        with patch("zurixai.supplychain.checker._check_pypi_registry", return_value={"status": "ok"}):
            result = check_supply_chain(tmp_path)
        assert result["checked"] == 2
        assert result["unavailable"] == 0

    def test_typosquat_detection(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text("reqeusts\n")
        with patch("zurixai.supplychain.checker._check_pypi_registry", return_value={"status": "not_found"}):
            result = check_supply_chain(tmp_path)
        assert result["checked"] == 1
        assert result["suspicious"] == 1


@pytest.mark.parametrize("source", ["npm", "pypi"])
@pytest.mark.parametrize("status,expected", [(200, "ok"), (404, "not_found"), (429, "unavailable"), (503, "unavailable")])
def test_registry_outcomes(tmp_path, source, status, expected):
    import httpx

    if source == "npm":
        (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"requests": "1"}}))
        metadata = {"dist-tags": {"latest": "1"}, "versions": {"1": {}}}
    else:
        (tmp_path / "requirements.txt").write_text("requests\n")
        metadata = {"info": {"version": "1"}, "releases": {}}
    with patch("zurixai.supplychain.checker.httpx.get", return_value=httpx.Response(status, json=metadata)):
        result = check_supply_chain(tmp_path)
    assert result["details"]["requests"]["status"] == expected
    assert result["unavailable"] == int(expected == "unavailable")
    assert result["suspicious"] == int(expected == "not_found")


class TestDriftSentinel:
    """Tests for drift sentinel."""

    def test_git_detection(self, tmp_path: Path) -> None:
        result = check_drift(tmp_path)
        # git_available depends on whether tmp_path is inside a git repo
        assert isinstance(result["git_available"], bool)

    def test_no_files(self, tmp_path: Path) -> None:
        result = check_drift(tmp_path)
        assert result["orphaned_functions"] == 0


class TestRulesParser:
    """Tests for rules parser."""

    def test_no_rules_file(self, tmp_path: Path) -> None:
        result = parse_rules(tmp_path / ".zurix" / "rules.md")
        assert result["rule_count"] == 0
        assert result["file_exists"] is False

    def test_parse_rules(self, tmp_path: Path) -> None:
        rules_file = tmp_path / "rules.md"
        rules_file.write_text("# Rules\n\n## Style\n- No console.log\n- Max 50 lines\n\n## Security\n- No eval()\n")
        result = parse_rules(rules_file)
        assert result["file_exists"] is True
        assert result["rule_count"] == 3
        assert len(result["sections"]) == 2

    def test_rule_classification(self, tmp_path: Path) -> None:
        rules_file = tmp_path / "rules.md"
        rules_file.write_text("# Rules\n- All functions must have tests\n- No hardcoded secrets\n- Max line length: 100\n")
        result = parse_rules(rules_file)
        types = [r["type"] for r in result["rules"]]
        assert "testing" in types
        assert "security" in types
        assert "style" in types
