"""ZurixAI Prompt Evaluation — lightweight eval without promptfoo dependency."""

from __future__ import annotations

import json
import time
from pathlib import Path


def evaluate_caveman(response: str) -> dict:
    """Evaluate if response follows Caveman protocol."""
    score = 0
    issues = []

    # Check for greetings (should be absent)
    greeting_patterns = ["hello", "hi there", "hey", "greetings", "welcome"]
    if any(g in response.lower() for g in greeting_patterns):
        issues.append("Contains greeting (should be absent)")
    else:
        score += 25

    # Check for bullet points (should be present)
    if "- " in response or "* " in response or "• " in response:
        score += 25
    else:
        issues.append("No bullet points found")

    # Check for excessive length (should be concise)
    if len(response) < 500:
        score += 25
    else:
        issues.append(f"Response too long ({len(response)} chars)")

    # Check for code blocks (should be present for code tasks)
    if "```" in response or "    " in response:
        score += 25
    else:
        issues.append("No code blocks found")

    return {
        "protocol": "caveman",
        "score": score,
        "max_score": 100,
        "passed": score >= 75,
        "issues": issues,
    }


def evaluate_ponytail(response: str, existing_code: str = "") -> dict:
    """Evaluate if response follows Ponytail protocol."""
    score = 0
    issues = []

    # Check for reuse suggestions (should be present)
    reuse_patterns = ["reuse", "existing", "already", "extend", "import"]
    if any(p in response.lower() for p in reuse_patterns):
        score += 30
    else:
        issues.append("No reuse suggestions found")

    # Check for "new code" warnings (should be minimal)
    new_code_patterns = ["write new", "create new", "implement from scratch"]
    if any(p in response.lower() for p in new_code_patterns):
        issues.append("Suggests writing new code unnecessarily")
    else:
        score += 30

    # Check for decision ladder reference
    if "1." in response or "step 1" in response.lower() or "first" in response.lower():
        score += 20
    else:
        issues.append("No decision ladder steps found")

    # Check for code examples
    if "```" in response or "def " in response or "function " in response:
        score += 20
    else:
        issues.append("No code examples found")

    return {
        "protocol": "ponytail",
        "score": score,
        "max_score": 100,
        "passed": score >= 75,
        "issues": issues,
    }


def run_evaluation(prompts_dir: str = "engine/llm/prompts") -> dict:
    """Run evaluation on all prompt files."""
    results = {
        "timestamp": time.time(),
        "prompts": {},
        "summary": {"total": 0, "passed": 0, "failed": 0},
    }

    prompts_path = Path(prompts_dir)
    if not prompts_path.exists():
        return results

    for prompt_file in prompts_path.glob("*.txt"):
        content = prompt_file.read_text()
        results["prompts"][prompt_file.name] = {
            "content": content,
            "length": len(content),
            "lines": len(content.splitlines()),
        }
        results["summary"]["total"] += 1

    return results


def save_results(results: dict, output_file: str = "eval_results/evaluation.json") -> None:
    """Save evaluation results to file."""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"Results saved to {output_file}")


if __name__ == "__main__":
    # Run evaluation
    results = run_evaluation()
    save_results(results)

    # Print summary
    print(f"\nPrompt Evaluation Summary:")
    print(f"  Total prompts: {results['summary']['total']}")
    print(f"  Passed: {results['summary']['passed']}")
    print(f"  Failed: {results['summary']['failed']}")

    # Show prompt details
    for name, data in results["prompts"].items():
        print(f"\n  {name}:")
        print(f"    Length: {data['length']} chars")
        print(f"    Lines: {data['lines']}")
