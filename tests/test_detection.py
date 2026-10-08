"""Detection accuracy tests: file walking, manifest parsing, local modules."""

from __future__ import annotations

from pathlib import Path

from zurixai.ast.npm_validator import validate_npm_imports
from zurixai.ast.pypi_validator import validate_pypi_imports
from zurixai.manifests import normalize_name, python_declared_deps
from zurixai.walk import iter_source_files


def _write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


class TestWalk:
    def test_skips_virtualenvs_git_and_vendor_dirs(self, tmp_path: Path) -> None:
        keep = _write(tmp_path / "app" / "main.py")
        for skipped in (".venv", "venv", ".git", "node_modules", "__pycache__", "site-packages"):
            _write(tmp_path / skipped / "lib" / "x.py")
        assert list(iter_source_files(tmp_path, {".py"})) == [keep]

    def test_does_not_skip_files_whose_names_contain_dist_or_build(self, tmp_path: Path) -> None:
        files = {_write(tmp_path / "distance.py"), _write(tmp_path / "rebuild" / "x.py")}
        assert set(iter_source_files(tmp_path, {".py"})) == files

    def test_filters_by_suffix(self, tmp_path: Path) -> None:
        js = _write(tmp_path / "a.js")
        _write(tmp_path / "b.py")
        assert list(iter_source_files(tmp_path, {".js"})) == [js]


class TestNormalizeName:
    def test_pep503(self) -> None:
        assert normalize_name("Foo_Bar.baz") == "foo-bar-baz"


class TestPythonDeclaredDeps:
    def test_unpinned_pep621_dependencies(self, tmp_path: Path) -> None:
        _write(tmp_path / "pyproject.toml",
               '[project]\nname = "demo"\ndependencies = ["requests>=2", "fastapi", "reqeusts"]\n')
        assert python_declared_deps(tmp_path) >= {"requests", "fastapi", "reqeusts"}

    def test_optional_and_dependency_groups(self, tmp_path: Path) -> None:
        _write(tmp_path / "pyproject.toml",
               '[project]\nname = "demo"\n'
               '[project.optional-dependencies]\ndev = ["pytest", "ruff[all]==0.5"]\n'
               '[dependency-groups]\nlint = ["mypy"]\n')
        assert python_declared_deps(tmp_path) >= {"pytest", "ruff", "mypy"}

    def test_poetry(self, tmp_path: Path) -> None:
        _write(tmp_path / "pyproject.toml",
               '[tool.poetry.dependencies]\npython = "^3.11"\nhttpx = "^0.27"\n'
               '[tool.poetry.group.dev.dependencies]\npytest = "*"\n')
        deps = python_declared_deps(tmp_path)
        assert {"httpx", "pytest"} <= deps
        assert "python" not in deps

    def test_requirements_variants(self, tmp_path: Path) -> None:
        _write(tmp_path / "requirements.txt", "Flask==3.0  # web\n-r requirements-dev.txt\n")
        _write(tmp_path / "requirements-dev.txt", "black; python_version>'3.8'\n")
        assert python_declared_deps(tmp_path) >= {"flask", "black"}

    def test_setup_py_install_requires(self, tmp_path: Path) -> None:
        _write(tmp_path / "setup.py",
               "from setuptools import setup\nsetup(name='demo', install_requires=['click>=8', 'Jinja2'])\n")
        assert python_declared_deps(tmp_path) >= {"click", "jinja2"}

    def test_invalid_toml_is_ignored(self, tmp_path: Path) -> None:
        _write(tmp_path / "pyproject.toml", "[project\n")
        assert python_declared_deps(tmp_path) == set()


class TestPyPIImports:
    def _project(self, tmp_path: Path, deps: str) -> Path:
        _write(tmp_path / "pyproject.toml", f'[project]\nname = "demo"\ndependencies = [{deps}]\n')
        return tmp_path

    def test_unpinned_declared_dependency_is_valid(self, tmp_path: Path) -> None:
        self._project(tmp_path, '"fastapi"')
        _write(tmp_path / "main.py", "from fastapi import FastAPI\n")
        result = validate_pypi_imports(tmp_path)
        assert (result["valid"], result["invalid"]) == (1, 0)

    def test_own_package_is_not_a_dependency(self, tmp_path: Path) -> None:
        self._project(tmp_path, "")
        _write(tmp_path / "app" / "__init__.py")
        _write(tmp_path / "app" / "util.py", "def helper(): return 1\n")
        _write(tmp_path / "main.py", "from app.util import helper\n")
        assert validate_pypi_imports(tmp_path)["invalid"] == 0

    def test_src_layout_package_is_local(self, tmp_path: Path) -> None:
        self._project(tmp_path, "")
        _write(tmp_path / "src" / "mypkg" / "__init__.py")
        _write(tmp_path / "tests" / "test_x.py", "import mypkg\n")
        assert validate_pypi_imports(tmp_path)["invalid"] == 0

    def test_sibling_module_is_local(self, tmp_path: Path) -> None:
        self._project(tmp_path, "")
        _write(tmp_path / "scripts" / "helpers.py")
        _write(tmp_path / "scripts" / "run.py", "import helpers\n")
        assert validate_pypi_imports(tmp_path)["invalid"] == 0

    def test_import_name_maps_to_distribution(self, tmp_path: Path) -> None:
        self._project(tmp_path, '"PyYAML", "Pillow", "python-dateutil"')
        _write(tmp_path / "main.py", "import yaml\nfrom PIL import Image\nfrom dateutil import tz\n")
        result = validate_pypi_imports(tmp_path)
        assert (result["valid"], result["invalid"]) == (3, 0)

    def test_google_client_imports_map_to_their_distributions(self, tmp_path: Path) -> None:
        self._project(tmp_path, '"google-api-python-client", "google-auth-oauthlib", "google-auth-httplib2"')
        _write(tmp_path / "main.py", "from googleapiclient.discovery import build\n"
                                     "from google_auth_oauthlib.flow import InstalledAppFlow\n"
                                     "import google_auth_httplib2\n")
        result = validate_pypi_imports(tmp_path)
        assert (result["valid"], result["invalid"]) == (3, 0)

    def test_undeclared_google_client_import_names_the_distribution(self, tmp_path: Path) -> None:
        self._project(tmp_path, '"requests"')
        _write(tmp_path / "main.py", "from googleapiclient.discovery import build\n")
        assert validate_pypi_imports(tmp_path)["undeclared"]["googleapiclient"]["package"] == "google-api-python-client"

    def test_undeclared_import_is_reported_with_package_and_files(self, tmp_path: Path) -> None:
        self._project(tmp_path, '"requests"')
        _write(tmp_path / "pkg" / "a.py", "import numpy\nimport cv2\n")
        _write(tmp_path / "pkg" / "b.py", "import numpy as np\n")
        result = validate_pypi_imports(tmp_path)
        assert result["invalid"] == 3
        assert result["undeclared"]["numpy"] == {"package": "numpy", "files": ["pkg/a.py", "pkg/b.py"]}
        assert result["undeclared"]["cv2"]["package"] == "opencv-python"

    def test_ignores_virtualenv(self, tmp_path: Path) -> None:
        self._project(tmp_path, "")
        _write(tmp_path / ".venv" / "lib" / "x.py", "import numpy\n")
        assert validate_pypi_imports(tmp_path)["checked_files"] == 0


class TestNpmImports:
    def _project(self, tmp_path: Path, deps: dict) -> Path:
        import json
        _write(tmp_path / "package.json", json.dumps({"name": "demo", **deps}))
        return tmp_path

    def test_side_effect_reexport_and_multiline_imports(self, tmp_path: Path) -> None:
        self._project(tmp_path, {"dependencies": {}})
        _write(tmp_path / "src" / "index.ts",
               'import "dotenv/config";\n'
               'export { z } from "zod";\n'
               'import {\n  a,\n  b,\n} from "lodash";\n')
        result = validate_npm_imports(tmp_path)
        assert set(result["undeclared"]) == {"dotenv", "zod", "lodash"}

    def test_peer_and_optional_dependencies_count_as_declared(self, tmp_path: Path) -> None:
        self._project(tmp_path, {"peerDependencies": {"react": "*"}, "optionalDependencies": {"fsevents": "*"}})
        _write(tmp_path / "a.js", 'const r = require("react");\nconst f = require("fsevents");\n')
        result = validate_npm_imports(tmp_path)
        assert (result["valid"], result["invalid"]) == (2, 0)

    def test_undeclared_reports_package_and_files(self, tmp_path: Path) -> None:
        self._project(tmp_path, {"dependencies": {}})
        _write(tmp_path / "src" / "a.js", 'import fp from "lodash/fp";\n')
        _write(tmp_path / "src" / "b.js", 'import _ from "lodash";\n')
        result = validate_npm_imports(tmp_path)
        assert result["undeclared"]["lodash"] == {"package": "lodash", "files": ["src/a.js", "src/b.js"]}

    def test_skips_build_output(self, tmp_path: Path) -> None:
        self._project(tmp_path, {"dependencies": {}})
        _write(tmp_path / ".next" / "server.js", 'require("x");\n')
        _write(tmp_path / "dist" / "index.js", 'require("x");\n')
        assert validate_npm_imports(tmp_path)["checked_files"] == 0

    def test_builtin_subpaths_are_not_packages(self, tmp_path: Path) -> None:
        self._project(tmp_path, {"dependencies": {}})
        _write(tmp_path / "a.mjs", 'import { readFile } from "fs/promises";\nimport a from "node:assert/strict";\n')
        assert validate_npm_imports(tmp_path)["invalid"] == 0


class TestSupplyChainCollection:
    def test_checks_unpinned_pyproject_and_all_npm_dep_fields(self, tmp_path: Path) -> None:
        import json
        from unittest.mock import patch

        from zurixai.supplychain.checker import check_supply_chain

        _write(tmp_path / "pyproject.toml", '[project]\nname = "demo"\ndependencies = ["requests>=2", "reqeusts"]\n')
        _write(tmp_path / "package.json", json.dumps({"peerDependencies": {"react": "*"}}))
        with patch("zurixai.supplychain.checker._check_pypi_registry", return_value={"status": "ok"}), \
             patch("zurixai.supplychain.checker._check_npm_registry", return_value={"status": "ok"}):
            result = check_supply_chain(tmp_path)
        assert set(result["details"]) == {"requests", "reqeusts", "react"}


class TestPhantomClassification:
    def _classify(self, npm: dict, pypi: dict, npm_status: dict, pypi_status: dict) -> dict:
        from unittest.mock import patch

        from zurixai.supplychain.checker import classify_undeclared

        with patch("zurixai.supplychain.checker._check_npm_registry",
                   side_effect=lambda name: {"status": npm_status[name]}), \
             patch("zurixai.supplychain.checker._check_pypi_registry",
                   side_effect=lambda name: {"status": pypi_status.get(name, "not_found")}):
            return classify_undeclared(npm, pypi)

    def test_missing_from_registry_is_phantom(self) -> None:
        pypi = {"huggingface_cli": {"package": "huggingface-cli", "files": ["main.py"]},
                "numpy": {"package": "numpy", "files": ["main.py"]}}
        result = self._classify({}, pypi, {}, {"huggingface-cli": "not_found", "numpy": "ok"})
        assert [p["name"] for p in result["phantom"]] == ["huggingface_cli"]
        assert result["phantom"][0] == {"name": "huggingface_cli", "package": "huggingface-cli",
                                        "source": "pypi", "files": ["main.py"]}
        assert [p["name"] for p in result["undeclared"]] == ["numpy"]

    def test_registry_outage_is_unverified_not_phantom(self) -> None:
        npm = {"left-pad-x": {"package": "left-pad-x", "files": ["a.js"]}}
        result = self._classify(npm, {}, {"left-pad-x": "unavailable"}, {})
        assert result["phantom"] == []
        assert [p["name"] for p in result["unverified"]] == ["left-pad-x"]

    def test_nothing_undeclared_makes_no_lookups(self) -> None:
        from unittest.mock import patch

        from zurixai.supplychain.checker import classify_undeclared

        with patch("zurixai.supplychain.checker.httpx.get") as get:
            result = classify_undeclared({}, {})
        get.assert_not_called()
        assert result == {"phantom": [], "undeclared": [], "unverified": []}


def _git(repo: Path, *args: str, date: str | None = None) -> None:
    import os
    import subprocess

    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    if date:
        env |= {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)


class TestDrift:
    def test_non_repo_reports_git_unavailable(self, tmp_path: Path) -> None:
        from zurixai.drift.sentinel import check_drift

        _write(tmp_path / "a.py", "def f(): pass\n")
        assert check_drift(tmp_path)["git_available"] is False

    def test_orphans(self, tmp_path: Path) -> None:
        from zurixai.drift.sentinel import check_drift

        _write(tmp_path / "app.py",
               "import functools\n"
               "def used(): return 1\n"
               "def never_called(): return 2\n"
               "def callback(x): return x\n"
               "def _private(): return 3\n"
               "@functools.cache\n"
               "def decorated(): return 4\n"
               "def test_something(): assert used()\n"
               "print(list(map(callback, [1])))\n")
        _write(tmp_path / "web.js",
               "export function publicApi() {}\n"
               "function deadHelper() {}\n"
               "const liveArrow = (a) => a;\n"
               "liveArrow(1);\n")
        orphans = check_drift(tmp_path)["orphaned_list"]
        assert sorted(orphans) == ["deadHelper in web.js", "never_called in app.py"]

    def test_stale_files_in_subdirectory_with_few_git_calls(self, tmp_path: Path) -> None:
        import subprocess
        from unittest.mock import patch

        from zurixai.drift.sentinel import check_drift

        _git(tmp_path, "init", "-q")
        for i in range(15):
            _write(tmp_path / "pkg" / f"old{i}.py", f"X{i} = {i}\n")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-qm", "old", date="2020-01-01T00:00:00")
        _write(tmp_path / "pkg" / "new.py", "Y = 1\n")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-qm", "new")

        with patch("zurixai.drift.sentinel.subprocess.run", wraps=subprocess.run) as run:
            result = check_drift(tmp_path / "pkg")
        stale = sorted(s["file"] for s in result["stale_list"])
        assert stale == sorted(f"old{i}.py" for i in range(15))
        assert run.call_count <= 3


class TestRealWorldFalsePositives:
    def test_guarded_and_type_checking_imports_are_optional(self, tmp_path: Path) -> None:
        _write(tmp_path / "pyproject.toml", '[project]\nname = "demo"\ndependencies = []\n')
        _write(tmp_path / "compat.py",
               "try:\n    import simplejson as json\nexcept ImportError:\n    import json\n"
               "try:\n    from http.server import HTTPServer\nexcept ImportError:\n"
               "    from BaseHTTPServer import HTTPServer\n")
        _write(tmp_path / "use.py", "from simplejson import JSONDecodeError\n")
        _write(tmp_path / "types_only.py",
               "import typing\nif typing.TYPE_CHECKING:\n    from typing_extensions import Buffer\n")
        assert validate_pypi_imports(tmp_path)["undeclared"] == {}

    def test_build_requires_nested_requirements_and_pygithub(self, tmp_path: Path) -> None:
        _write(tmp_path / "pyproject.toml",
               '[build-system]\nrequires = ["setuptools>=61"]\n'
               '[project]\nname = "demo"\ndependencies = []\n'
               '[dependency-groups]\nci = ["PyGithub"]\n')
        _write(tmp_path / "docs" / "requirements.txt", "Pygments\n")
        _write(tmp_path / "setup.py", "import setuptools\n")
        _write(tmp_path / "docs" / "conf.py", "from pygments.style import Style\n")
        _write(tmp_path / "scripts" / "deploy.py", "from github import Github\n")
        assert validate_pypi_imports(tmp_path)["undeclared"] == {}

    def test_js_comments_urls_and_invalid_names_are_ignored(self, tmp_path: Path) -> None:
        import json
        _write(tmp_path / "package.json", json.dumps({"name": "demo"}))
        _write(tmp_path / "src" / "index.ts",
               "/**\n * @example\n * import { chunk } from 'some-doc-example';\n */\n"
               "// import x from 'commented-out';\n"
               "import remote from 'https://esm.sh/preact';\n"
               "const code = `import { x } from '${pkg}'`;\n")
        _write(tmp_path / ".yarn" / "releases" / "yarn.cjs", "require('))&&ee(');require('real-looking');\n")
        _write(tmp_path / "vendor.min.js", "require('minified-dep');\n")
        assert validate_npm_imports(tmp_path)["undeclared"] == {}

    def test_nested_package_json_and_workspace_names(self, tmp_path: Path) -> None:
        import json
        _write(tmp_path / "package.json", json.dumps({"name": "root", "workspaces": ["bench", "docs"]}))
        _write(tmp_path / "bench" / "package.json", json.dumps({"name": "bench", "devDependencies": {"lodash": "*"}}))
        _write(tmp_path / "docs" / "package.json", json.dumps({"name": "@root/docs"}))
        _write(tmp_path / "bench" / "run.ts", "import _ from 'lodash';\nimport d from '@root/docs';\n")
        _write(tmp_path / "src" / "a.ts", "import _ from 'lodash';\n")
        undeclared = validate_npm_imports(tmp_path)["undeclared"]
        assert list(undeclared) == ["lodash"]
        assert undeclared["lodash"]["files"] == ["src/a.ts"]


class TestPhantomAccuracy:
    def test_removed_stdlib_modules_are_never_dependencies(self, tmp_path: Path) -> None:
        _write(tmp_path / "pyproject.toml", '[project]\nname = "demo"\ndependencies = []\n')
        _write(tmp_path / "legacy.py", "import imghdr\nimport cgi\nimport asyncore\nimport imp\nfrom distutils import core\n")
        assert validate_pypi_imports(tmp_path)["undeclared"] == {}

    def test_py_suffixed_distribution_counts_as_declared(self, tmp_path: Path) -> None:
        _write(tmp_path / "pyproject.toml",
               '[project]\nname = "demo"\ndependencies = ["markdown-it-py", "linkify-it-py"]\n')
        _write(tmp_path / "md.py", "import markdown_it\nimport linkify_it\n")
        result = validate_pypi_imports(tmp_path)
        assert (result["valid"], result["invalid"]) == (2, 0)

    def test_phantom_lookup_tries_common_spellings(self) -> None:
        from unittest.mock import patch

        from zurixai.supplychain.checker import classify_undeclared

        exists = {"markdown-it-py"}
        with patch("zurixai.supplychain.checker._check_pypi_registry",
                   side_effect=lambda n: {"status": "ok" if n in exists else "not_found"}):
            result = classify_undeclared({}, {"markdown_it": {"package": "markdown-it", "files": ["a.py"]},
                                              "totally_made_up": {"package": "totally-made-up", "files": ["a.py"]}})
        assert [(x["name"], x["package"]) for x in result["undeclared"]] == [("markdown_it", "markdown-it-py")]
        assert [x["name"] for x in result["phantom"]] == ["totally_made_up"]

    def test_config_only_folders_are_not_local_modules(self, tmp_path: Path) -> None:
        _write(tmp_path / "pyproject.toml", '[project]\nname = "demo"\ndependencies = []\n')
        _write(tmp_path / "docker" / "Dockerfile", "FROM python\n")
        _write(tmp_path / "app" / "redis" / "redis.conf", "port 6379\n")
        _write(tmp_path / "app" / "main.py", "import docker\nimport redis\n")
        assert set(validate_pypi_imports(tmp_path)["undeclared"]) == {"docker", "redis"}


class TestRealPRFalsePositives:
    def test_vcs_and_url_requirement_lines_are_not_package_names(self, tmp_path: Path) -> None:
        _write(tmp_path / "requirements-docs.txt",
               "git+https://${TOKEN}@github.com/org/private-theme.git@1.0\n"
               "https://example.com/wheels/foo-1.0-py3-none-any.whl\n"
               "./local-pkg\n"
               "mkdocs @ git+https://github.com/mkdocs/mkdocs.git\n")
        assert python_declared_deps(tmp_path) == {"mkdocs"}

    def test_pdm_backend_provides_pdm_module(self, tmp_path: Path) -> None:
        _write(tmp_path / "pyproject.toml",
               '[build-system]\nrequires = ["pdm-backend"]\n[project]\nname = "demo"\ndependencies = []\n')
        _write(tmp_path / "pdm_build.py", "from pdm.backend.hooks import Context\n")
        assert validate_pypi_imports(tmp_path)["undeclared"] == {}

    def test_shallow_clone_skips_stale_detection(self, tmp_path: Path) -> None:
        from zurixai.drift.sentinel import check_drift

        origin = tmp_path / "origin"
        _write(origin / "old.py", "X = 1\n")
        _git(origin, "init", "-q")
        _git(origin, "add", "-A")
        _git(origin, "commit", "-qm", "old", date="2020-01-01T00:00:00")
        clone = tmp_path / "clone"
        _git(tmp_path, "clone", "-q", "--depth=1", f"file://{origin}", str(clone))
        result = check_drift(clone)
        assert result["stale_files"] == 0
        assert result["stale_skipped"] == "shallow clone"
