"""CLI behaviour: argument parsing, target path, exit codes, output."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from zurixai.__main__ import main


def _registry(status_by_name: dict[str, int]):
    """Fake registry: a name mapped to 404 is missing under every common spelling; others exist."""
    missing = {spelling for name, code in status_by_name.items() if code == 404
               for spelling in (name, f"{name}-py", f"py{name}", f"python-{name}")}

    def get(url: str, **_: object) -> httpx.Response:
        name = url.rstrip("/").split("/")[-2 if url.endswith("/json") else -1]
        status = 404 if name in missing else status_by_name.get(name, 200)
        return httpx.Response(status, json={"info": {"version": "1"}, "releases": {}, "dist-tags": {}})
    return patch("zurixai.supplychain.checker.httpx.get", side_effect=get)


def _run(argv: list[str]) -> int:
    with pytest.raises(SystemExit) as exc:
        main(argv)
    return int(exc.value.code or 0)


@pytest.fixture
def clean_project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\ndependencies = ["requests"]\n')
    (tmp_path / "main.py").write_text("import requests\nrequests.get('x')\n")
    return tmp_path


@pytest.fixture
def broken_project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\ndependencies = []\n')
    (tmp_path / "main.py").write_text("import numpy\nimport huggingface_cli\n")
    return tmp_path


def test_top_level_help_lists_real_commands(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(["--help"]) == 0
    out = capsys.readouterr().out
    for command in ("check", "init", "verify", "tui"):
        assert command in out
    assert "scan" not in out


def test_check_help_does_not_scan(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("zurixai.cli.check.run_checks") as run_checks:
        assert _run(["check", "--help"]) == 0
    run_checks.assert_not_called()
    assert "path" in capsys.readouterr().out


def test_check_scans_the_given_path_not_cwd(broken_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with _registry({}):
        _run(["check", str(broken_project), "--json"])
    report = json.loads(capsys.readouterr().out)
    assert report["project"] == str(broken_project.resolve())
    assert report["checks"]["pypi_imports"]["invalid"] == 2


def test_missing_path_is_a_usage_error(tmp_path: Path) -> None:
    assert _run(["check", str(tmp_path / "nope")]) == 2


def test_exit_code_is_zero_when_clean(clean_project: Path) -> None:
    with _registry({}):
        assert _run(["check", str(clean_project), "--no-color"]) == 0


def test_exit_code_is_one_on_critical_findings(broken_project: Path) -> None:
    with _registry({}):
        assert _run(["check", str(broken_project), "--no-color"]) == 1


def test_phantoms_are_reported_separately(broken_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with _registry({"huggingface-cli": 404}):
        _run(["check", str(broken_project), "--json"])
    imports = json.loads(capsys.readouterr().out)["checks"]["imports"]
    assert [p["name"] for p in imports["phantom"]] == ["huggingface_cli"]
    assert [p["name"] for p in imports["undeclared"]] == ["numpy"]

    with _registry({"huggingface-cli": 404}):
        _run(["check", str(broken_project), "--no-color"])
    text = capsys.readouterr().out
    assert "huggingface_cli" in text and "not found" in text.lower()
    assert "LLM" not in text and "--pro" not in text


def test_init_needs_no_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                               capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    assert _run(["init"]) == 0
    config = json.loads((tmp_path / ".zurix" / "config.json").read_text())
    assert "api_key" not in config and "engine_url" not in config
    out = capsys.readouterr().out
    assert "API key" not in out and "API_KEY" not in out and "--pro" not in out
