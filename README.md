# ZurixAI

Catch broken packages, phantom imports, and schema drift before they reach production.

ZurixAI is an agentic quality and verification engine for AI-generated code. It runs as a CLI tool or GitHub App, scanning every PR for hallucinated packages, broken imports, supply-chain risks, and schema drift.

## Quick start

```bash
pip install git+https://github.com/HuziM/zurixai
zurix check .
```

## Features

- **Supply chain checks** — registry metadata, typosquatting detection, phantom import triage
- **AST import validation** — Python and JavaScript/TypeScript import verification
- **Drift detection** — orphaned functions, stale files
- **Rules engine** — define quality rules in `.zurix/rules.md`
- **Schema detection** — TypeScript, GraphQL, OpenAPI, JSON Schema drift
- **Stack trace parsing** — paste a stack trace, get a structured breakdown and stub failing test
- **Micro-mock test generation** — auto-discover tests, generate minimal failing tests from AST
- **Interactive TUI** — terminal-native dashboard via Textual

## Commands

```bash
zurix check .          # Run all checks
zurix init             # Scaffold .zurix/config.json + rules.md
zurix tui              # Open interactive dashboard
zurix version          # Print version
```

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
  cli/              # CLI entry points (check, init)
  client/           # API client for hosted service
  config.py         # Configuration loader
  drift/            # Orphan/stale file detection
  eval/             # Evaluation harness
  exec/             # Test discovery, generation, sandboxed execution
  formatters/       # Output formatters
  rules/            # Rules engine (parse .zurix/rules.md)
  schema/           # Schema detection + migration patches
  supplychain/      # Registry checks, typosquatting, suspicion scoring
  tui/              # Interactive terminal dashboard
```

## License

MIT — see [LICENSE](LICENSE).

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting.
