"""ZurixAI Auto-Select — automatically select best prompt variant."""

from __future__ import annotations

import json
from pathlib import Path


def select_best_prompt(results_file: str) -> str:
    """Select the best prompt variant from optimization results."""
    results_path = Path(results_file)
    if not results_path.exists():
        return ""

    with open(results_path) as f:
        results = json.load(f)

    # Sort by score (highest first)
    sorted_results = sorted(results, key=lambda x: x.get("score", 0), reverse=True)

    if sorted_results:
        return sorted_results[0].get("prompt", "")
    return ""


def load_prompt_version(prompt_dir: str, version: str = "latest") -> str:
    """Load a specific prompt version."""
    prompt_path = Path(prompt_dir) / f"{version}.txt"
    if prompt_path.exists():
        return prompt_path.read_text()
    return ""


def save_prompt_version(prompt_dir: str, version: str, content: str) -> None:
    """Save a prompt version."""
    prompt_path = Path(prompt_dir) / f"{version}.txt"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(content)
