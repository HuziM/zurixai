"""Rules Parser — reads .zurix/rules.md for custom rule enforcement."""

from __future__ import annotations

import re
from pathlib import Path


def parse_rules(rules_file: Path) -> dict:
    """Parse .zurix/rules.md and extract structured rules."""
    result = {
        "rule_count": 0,
        "rules": [],
        "sections": [],
        "file_exists": False,
    }

    if not rules_file.exists():
        return result

    result["file_exists"] = True

    try:
        content = rules_file.read_text()
    except Exception:
        return result

    # Parse sections and their rules
    current_section = "general"
    sections = []

    for line in content.splitlines():
        stripped = line.strip()

        # Detect section headers
        if stripped.startswith("## "):
            current_section = stripped[3:].strip()
            sections.append(current_section)
            continue

        # Parse rules (lines starting with -, *, or numbered)
        rule_text = None
        if stripped.startswith("- ") or stripped.startswith("* "):
            rule_text = stripped[2:].strip()
        elif len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in (".", ")"):
            rule_text = stripped[2:].strip()
        elif stripped.startswith("- ["):
            # Checkbox: - [ ] or - [x]
            match = re.match(r"^-\s*\[[ x]\]\s*(.+)$", stripped)
            if match:
                rule_text = match.group(1).strip()

        if rule_text:
            result["rules"].append({
                "text": rule_text,
                "type": _classify_rule(rule_text, current_section),
                "section": current_section,
            })

    result["sections"] = sections
    result["rule_count"] = len(result["rules"])

    return result


def _classify_rule(rule_text: str, section: str) -> str:
    """Classify a rule into a category using section context + keywords."""
    text_lower = rule_text.lower()

    # Context-aware: use section name if it provides clear signal
    section_lower = section.lower()
    if "test" in section_lower or "spec" in section_lower:
        return "testing"
    elif "security" in section_lower or "auth" in section_lower:
        return "security"
    elif "style" in section_lower or "format" in section_lower:
        return "style"
    elif "doc" in section_lower:
        return "documentation"

    # Keyword-based classification (order matters: more specific first)
    # Testing keywords (check before "security" to avoid "eval" false positives)
    testing_kw = ["test", "coverage", "spec", "assert", "mock", "fixture"]
    if any(kw in text_lower for kw in testing_kw):
        return "testing"

    # Security keywords (excluding "eval" which is ambiguous)
    security_kw = ["secret", "credential", "auth", "token", "password", "injection",
                    "xss", "csrf", "sql", "hardcode"]
    if any(kw in text_lower for kw in security_kw):
        return "security"

    # Style keywords
    style_kw = ["style", "format", "indent", "line length", "lint", "prettier"]
    if any(kw in text_lower for kw in style_kw):
        return "style"

    # Documentation keywords
    doc_kw = ["comment", "docstring", "documentation", "readme", "javadoc"]
    if any(kw in text_lower for kw in doc_kw):
        return "documentation"

    return "general"
