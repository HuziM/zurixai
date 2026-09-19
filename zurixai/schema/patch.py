"""Deterministic migration patch skeletons for schema changes.

The patch is a mechanical migration plan, not an LLM-authored diff. It is
clearly marked so callers know the AI body is disabled.
"""

from __future__ import annotations

from pathlib import Path

_CHANGE_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("rename", ("rename", "renamed", "renaming")),
    ("remove_field", ("remove", "delete", "drop", "deprecate")),
    ("add_field", ("add", "new field", "introduce", "append")),
    ("type_change", ("change type", "type change", "retype", "widen", "narrow")),
)


def classify_change(description: str) -> str:
    """Classify a change description into a coarse migration kind."""
    lowered = description.lower()
    for kind, keywords in _CHANGE_HINTS:
        if any(keyword in lowered for keyword in keywords):
            return kind
    return "unknown"


def _relative(path: str, root: Path | None) -> str:
    if root is None:
        return path
    try:
        return str(Path(path).resolve().relative_to(root.resolve()))
    except ValueError:
        return path


def generate_migration_patch(
    definition_name: str,
    schema_type: str,
    change_description: str,
    references: list[dict],
    root: str | Path | None = None,
) -> dict:
    """Build a migration patch skeleton and its affected file set."""
    root_path = Path(root) if root else None
    change_kind = classify_change(change_description)
    affected = sorted({_relative(ref["file"], root_path) for ref in references})

    lines = [
        "# Migration patch — skeleton (AI disabled)",
        f"# target: {definition_name} ({schema_type})",
        f"# change: {change_description or 'unspecified'} [{change_kind}]",
        f"# references: {len(references)} across {len(affected)} file(s)",
        "",
    ]
    if not affected:
        lines.append(f"# No references found for {definition_name}; nothing to patch.")
    for file_name in affected:
        lines.extend(
            [
                f"--- a/{file_name}",
                f"+++ b/{file_name}",
                f"@@ migrate {definition_name} ({change_kind}) @@",
                f"-  # TODO: previous {definition_name} usage",
                f"+  # TODO: apply {change_kind} for {definition_name}",
                "",
            ]
        )

    confidence = 0.4 if change_kind != "unknown" and affected else 0.25
    return {
        "migration_patch": "\n".join(lines),
        "affected_files": affected,
        "confidence": confidence,
        "change_kind": change_kind,
        "definition_name": definition_name,
    }
