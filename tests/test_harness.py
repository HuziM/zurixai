"""ZurixAI Test Harness — Regressive testing across iterations."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path


REPOS = {
    "nanoid": "https://github.com/ai/nanoid.git",
    "es-toolkit": "https://github.com/toss/es-toolkit.git",
    "requests": "https://github.com/psf/requests.git",
}

TEST_DIR = Path("/tmp/zurix-test")
RESULTS_DIR = Path("eval_results")


def clone_repo(name: str, url: str) -> Path:
    """Clone a repository for testing."""
    repo_dir = TEST_DIR / name
    if repo_dir.exists():
        shutil.rmtree(repo_dir)
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--depth", "1", url, str(repo_dir)], check=True)
    return repo_dir


def run_checks(repo_dir: Path) -> dict:
    """Run all ZurixAI checks on a repository."""
    from zurixai.ast.npm_validator import validate_npm_imports
    from zurixai.ast.pypi_validator import validate_pypi_imports
    from zurixai.supplychain.checker import check_supply_chain
    from zurixai.drift.sentinel import check_drift
    from zurixai.rules.parser import parse_rules

    start = time.time()

    npm = validate_npm_imports(repo_dir)
    pypi = validate_pypi_imports(repo_dir)
    supply = check_supply_chain(repo_dir)
    drift = check_drift(repo_dir)
    rules = parse_rules(repo_dir / ".zurix" / "rules.md")

    elapsed = time.time() - start

    return {
        "repo": repo_dir.name,
        "scan_time_seconds": round(elapsed, 2),
        "checks": {
            "npm_imports": npm,
            "pypi_imports": pypi,
            "supply_chain": supply,
            "drift": drift,
            "rules": rules,
        },
    }


def save_results(results: dict, iteration: int) -> None:
    """Save iteration results."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_file = RESULTS_DIR / f"iteration_{iteration}_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved to {output_file}")


def cleanup() -> None:
    """Clean up temp files."""
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)
    # Don't delete final summary
    for f in RESULTS_DIR.glob("iteration_*.json"):
        if "final" not in f.name:
            f.unlink()
    print("Cleanup complete.")


if __name__ == "__main__":
    import sys

    iteration = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    print(f"\n{'='*60}")
    print(f"ZurixAI Test Harness — Iteration {iteration}")
    print(f"{'='*60}\n")

    # Clone repos
    for name, url in REPOS.items():
        print(f"Cloning {name}...")
        repo_dir = clone_repo(name, url)
        print(f"  Cloned to {repo_dir}")

    # Run checks
    all_results = {}
    for name in REPOS:
        repo_dir = TEST_DIR / name
        print(f"\nRunning checks on {name}...")
        results = run_checks(repo_dir)
        all_results[name] = results

        # Print summary
        checks = results["checks"]
        print(f"  Scan time: {results['scan_time_seconds']}s")
        print(f"  npm imports: {checks['npm_imports']['valid']} valid, {checks['npm_imports']['invalid']} invalid")
        print(f"  Supply chain: {checks['supply_chain']['checked']} checked, {checks['supply_chain']['suspicious']} suspicious")
        print(f"  Drift: {checks['drift']['orphaned_functions']} orphaned, {checks['drift']['stale_files']} stale")

    # Save results
    save_results(all_results, iteration)

    # Cleanup
    cleanup()

    print(f"\n{'='*60}")
    print(f"Iteration {iteration} complete.")
    print(f"{'='*60}")
