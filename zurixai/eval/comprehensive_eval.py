"""ZurixAI Comprehensive Prompt Evaluation — tests actual prompt quality."""

from __future__ import annotations

import json
import re
from pathlib import Path


def evaluate_caveman_quality(prompt_content: str) -> dict:
    """Evaluate Caveman protocol quality based on content analysis."""
    score = 0
    details = []

    # 1. Structure (25 points)
    if "NEVER:" in prompt_content or "DO NOT:" in prompt_content:
        score += 10
        details.append("✅ Has explicit 'NEVER' rules")
    else:
        details.append("❌ Missing explicit 'NEVER' rules")

    if "EXAMPLE" in prompt_content or "example" in prompt_content.lower():
        score += 15
        details.append("✅ Has examples")
    else:
        details.append("❌ Missing examples")

    # 2. Clarity (25 points)
    if re.search(r'\d+\.', prompt_content):  # Numbered steps
        score += 10
        details.append("✅ Has numbered steps/structure")
    else:
        details.append("❌ Missing numbered structure")

    if "```" in prompt_content:  # Code blocks in examples
        score += 15
        details.append("✅ Has code block examples")
    else:
        details.append("❌ Missing code block examples")

    # 3. Conciseness (25 points)
    lines = [l for l in prompt_content.split('\n') if l.strip()]
    if len(lines) < 50:
        score += 15
        details.append(f"✅ Concise ({len(lines)} lines)")
    else:
        details.append(f"⚠️ Long ({len(lines)} lines)")

    if len(prompt_content) < 2000:
        score += 10
        details.append(f"✅ Good length ({len(prompt_content)} chars)")
    else:
        details.append(f"⚠️ Too long ({len(prompt_content)} chars)")

    # 4. Completeness (25 points)
    required_elements = ["bullet", "code", "token", "greeting"]
    found = sum(1 for e in required_elements if e in prompt_content.lower())
    score += int((found / len(required_elements)) * 25)
    details.append(f"✅ Found {found}/{len(required_elements)} key elements")

    return {
        "protocol": "caveman",
        "score": score,
        "max_score": 100,
        "passed": score >= 75,
        "details": details,
    }


def evaluate_ponytail_quality(prompt_content: str) -> dict:
    """Evaluate Ponytail protocol quality based on content analysis."""
    score = 0
    details = []

    # 1. Decision Ladder (30 points)
    if "Step 1:" in prompt_content or "Step 1:" in prompt_content:
        score += 15
        details.append("✅ Has Step 1 (search codebase)")
    else:
        details.append("❌ Missing Step 1")

    if "Step 2:" in prompt_content:
        score += 15
        details.append("✅ Has Step 2 (check stdlib)")
    else:
        details.append("❌ Missing Step 2")

    # 2. Examples (30 points)
    example_count = prompt_content.lower().count("example")
    if example_count >= 2:
        score += 20
        details.append(f"✅ Has {example_count} examples")
    elif example_count >= 1:
        score += 10
        details.append(f"✅ Has {example_count} example")
    else:
        details.append("❌ Missing examples")

    if "```" in prompt_content:
        score += 10
        details.append("✅ Has code block examples")
    else:
        details.append("❌ Missing code block examples")

    # 3. Reuse Emphasis (20 points)
    reuse_words = ["reuse", "existing", "extend", "import"]
    found = sum(1 for w in reuse_words if w in prompt_content.lower())
    score += min(found * 5, 20)
    details.append(f"✅ Found {found} reuse-related terms")

    # 4. Structure (20 points)
    if re.search(r'\d+\.', prompt_content):
        score += 10
        details.append("✅ Has numbered structure")
    else:
        details.append("❌ Missing numbered structure")

    if len(prompt_content) < 3000:
        score += 10
        details.append(f"✅ Good length ({len(prompt_content)} chars)")
    else:
        details.append(f"⚠️ Too long ({len(prompt_content)} chars)")

    return {
        "protocol": "ponytail",
        "score": score,
        "max_score": 100,
        "passed": score >= 75,
        "details": details,
    }


def evaluate_task_prompt_quality(prompt_content: str, task_name: str) -> dict:
    """Evaluate task-specific prompt quality."""
    score = 0
    details = []

    # 1. Has INPUT section
    if "INPUT:" in prompt_content or "Input:" in prompt_content:
        score += 20
        details.append("✅ Has INPUT section")
    else:
        details.append("❌ Missing INPUT section")

    # 2. Has PROCESS/Steps
    if "PROCESS:" in prompt_content or "Step" in prompt_content:
        score += 20
        details.append("✅ Has PROCESS/steps")
    else:
        details.append("❌ Missing PROCESS/steps")

    # 3. Has OUTPUT FORMAT
    if "OUTPUT" in prompt_content:
        score += 20
        details.append("✅ Has OUTPUT FORMAT")
    else:
        details.append("❌ Missing OUTPUT FORMAT")

    # 4. Has examples
    if "EXAMPLE" in prompt_content or "example" in prompt_content.lower():
        score += 20
        details.append("✅ Has examples")
    else:
        details.append("❌ Missing examples")

    # 5. Has RULES
    if "RULES:" in prompt_content or "RULES" in prompt_content:
        score += 20
        details.append("✅ Has RULES")
    else:
        details.append("❌ Missing RULES")

    return {
        "task": task_name,
        "score": score,
        "max_score": 100,
        "passed": score >= 75,
        "details": details,
    }


def run_comprehensive_evaluation(prompts_dir: str = "engine/llm/prompts") -> dict:
    """Run comprehensive evaluation on all prompt files."""
    results = {
        "timestamp": __import__('time').time(),
        "prompts": {},
        "summary": {"total": 0, "passed": 0, "failed": 0, "avg_score": 0},
    }

    prompts_path = Path(prompts_dir)
    if not prompts_path.exists():
        return results

    total_score = 0

    for prompt_file in prompts_path.glob("*.txt"):
        content = prompt_file.read_text()
        name = prompt_file.stem

        # Evaluate based on prompt type
        if name == "caveman":
            eval_result = evaluate_caveman_quality(content)
        elif name == "ponytail":
            eval_result = evaluate_ponytail_quality(content)
        elif name == "system":
            # System prompt combines both protocols
            caveman_score = evaluate_caveman_quality(content)
            ponytail_score = evaluate_ponytail_quality(content)
            eval_result = {
                "protocol": "system",
                "score": (caveman_score["score"] + ponytail_score["score"]) // 2,
                "max_score": 100,
                "passed": (caveman_score["score"] + ponytail_score["score"]) // 2 >= 75,
                "details": caveman_score["details"] + ponytail_score["details"],
            }
        else:
            eval_result = evaluate_task_prompt_quality(content, name)

        results["prompts"][name] = {
            "content_preview": content[:200] + "..." if len(content) > 200 else content,
            "length": len(content),
            "lines": len(content.splitlines()),
            "evaluation": eval_result,
        }

        results["summary"]["total"] += 1
        if eval_result["passed"]:
            results["summary"]["passed"] += 1
        else:
            results["summary"]["failed"] += 1
        total_score += eval_result["score"]

    if results["summary"]["total"] > 0:
        results["summary"]["avg_score"] = total_score // results["summary"]["total"]

    return results


def print_results(results: dict) -> None:
    """Pretty-print evaluation results."""
    print("\n" + "=" * 60)
    print("ZurixAI Prompt Quality Evaluation")
    print("=" * 60)

    for name, data in results["prompts"].items():
        eval_data = data["evaluation"]
        status = "✅ PASS" if eval_data["passed"] else "❌ FAIL"
        score = eval_data["score"]

        print(f"\n{name}: {status} ({score}/{eval_data['max_score']})")
        print(f"  Length: {data['length']} chars, {data['lines']} lines")

        for detail in eval_data.get("details", []):
            print(f"    {detail}")

    print("\n" + "-" * 60)
    print(f"Summary: {results['summary']['passed']}/{results['summary']['total']} passed")
    print(f"Average Score: {results['summary']['avg_score']}/100")
    print("=" * 60)


if __name__ == "__main__":
    results = run_comprehensive_evaluation()
    print_results(results)

    # Save results
    output_path = Path("eval_results/comprehensive_evaluation.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {output_path}")
