# ZurixAI

Catch broken packages, phantom imports, and schema drift before they reach production.

ZurixAI is an agentic quality and verification engine for AI-generated code. It runs as a CLI tool or GitHub App, scanning every PR for hallucinated packages, broken imports, supply-chain risks, and schema drift.

## Quick start

```bash
pip install git+https://github.com/HuziM/zurixai
zurix check .
```

## Features

- **Phantom import detection** — every import not declared in your manifest is looked up on npm/PyPI and reported as *phantom* (the package doesn't exist), *missing dependency* (it exists but isn't declared) or *unverified* (registry unreachable)
- **Import validation** — Python (`pyproject.toml`, requirements files, `setup.py`, Poetry) and JavaScript/TypeScript (nearest `package.json`, workspaces)
- **Supply chain checks** — registry metadata, deprecation, typosquatting heuristics for declared dependencies
- **Drift detection** — orphaned functions, stale files
- **Rules** — define quality rules in `.zurix/rules.md` (loaded and classified; enforcement is coming)
- **Schema detection** — TypeScript, GraphQL, OpenAPI, JSON Schema drift
- **Stack trace parsing** — paste a stack trace, get a structured breakdown and stub failing test
- **Micro-mock test generation** — auto-discover tests, generate minimal failing tests from AST
- **Interactive TUI** — terminal-native dashboard via Textual

## Commands

```bash
zurix check [PATH]     # Run all checks (default: current directory)
zurix check --json     # Machine-readable output
zurix init             # Scaffold .zurix/config.json + rules.md
zurix verify <audit.json> [--key <pubkey_hex>]   # Verify a signed audit report
zurix tui              # Open interactive dashboard
zurix --help           # All commands and options
```

`zurix check` exits `1` when it finds critical issues (phantom or undeclared imports, packages missing from their registry), so it can gate CI. No API key or account is needed.

## Rules

Define quality rules in `.zurix/rules.md`:

```markdown
# Rules

## Security
- No hardcoded secrets
- Use parameterized queries

## Testing
- All public functions must have tests
- No `time.sleep` in tests
```

## Architecture

```
zurixai/
  ast/              # Import validation (npm + PyPI)
  bugtrace/         # Stack trace parsing + stub test generation
  cli/              # CLI entry points (check, init, verify)
  config.py         # Configuration loader
  drift/            # Orphan/stale file detection
  exec/             # Test discovery, generation, sandboxed execution
  manifests.py      # Declared-dependency parsing for Python projects
  rules/            # Rules engine (parse .zurix/rules.md)
  schema/           # Schema detection + migration patches
  supplychain/      # Registry checks, typosquatting, suspicion scoring
  tui/              # Interactive terminal dashboard
  walk.py           # File walker (skips venvs, VCS, vendored and build dirs, symlinks)
```

## License

MIT — see [LICENSE](LICENSE).

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting.
