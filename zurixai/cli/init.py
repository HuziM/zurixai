"""zurix init — Initialize ZurixAI configuration for this project."""

from __future__ import annotations

import json
import os
from pathlib import Path

from zurixai.config import Config


def cmd_init(cfg: Config, args: list[str]) -> None:
    """Initialize .zurix/ directory and config for this project."""
    project_dir = Path.cwd()
    zurix_dir = project_dir / ".zurix"
    config_file = zurix_dir / "config.json"
    rules_file = zurix_dir / "rules.md"

    # Create .zurix/ directory
    zurix_dir.mkdir(parents=True, exist_ok=True)

    # Create config.json if not exists
    if not config_file.exists():
        default_config = {
            "project_name": project_dir.name,
            "engine_url": cfg.engine_url,
            "api_key": cfg.api_key or "YOUR_API_KEY_HERE",
            "plan": "free",
            "checks": {
                "ast_imports": True,
                "supply_chain": True,
                "drift": True,
                "rules": True,
            },
        }
        config_file.write_text(json.dumps(default_config, indent=2))
        print(f"✅ Created {config_file}")
    else:
        print(f"ℹ️  {config_file} already exists, skipping")

    # Create rules.md if not exists
    if not rules_file.exists():
        default_rules = """# ZurixAI Rules

## Code Style
- No console.log in production code
- All functions must have docstrings
- Max function length: 50 lines

## Security
- No hardcoded secrets
- No eval() usage
- No innerHTML assignment

## Testing
- All new functions must have tests
- Test coverage minimum: 80%

## Custom Rules
<!-- Add your custom rules below -->
"""
        rules_file.write_text(default_rules)
        print(f"✅ Created {rules_file}")
    else:
        print(f"ℹ️  {rules_file} already exists, skipping")

    # Print instructions
    print("\n" + "=" * 50)
    print("ZurixAI Initialized")
    print("=" * 50)
    print(f"\nProject: {project_dir.name}")
    print(f"Config: {config_file}")
    print(f"Rules: {rules_file}")
    print("\nNext steps:")
    print("1. Edit .zurix/rules.md to add your custom rules")
    print("2. Set your API key: export ZURIX_API_KEY=your_key")
    print("3. Run: zurix check")
    print("\nFor Pro features (LLM-powered patches):")
    print("1. Get your API key at https://zurixai.com/pricing")
    print("2. Set: export ZURIX_API_KEY=your_pro_key")
    print("3. Run: zurix check --pro")
    print("=" * 50)
