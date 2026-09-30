"""Entry point for `zurix` / `python -m zurixai`."""

from __future__ import annotations

import argparse
import sys

from zurixai import __version__
from zurixai.config import get_config


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zurix",
        description="Catch phantom imports, broken packages and drift in AI-written code.",
    )
    parser.add_argument("--version", action="version", version=f"zurixai {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="<command>")

    check = commands.add_parser(
        "check", help="run all checks on a project",
        description="Run all checks. Exits 1 when critical issues are found.",
    )
    check.add_argument("path", nargs="?", default=".", help="project directory (default: current directory)")
    check.add_argument("--json", action="store_true", help="print machine-readable JSON")
    check.add_argument("--list", action="store_true", help="list available checks and exit")
    check.add_argument("--no-color", action="store_true", help="disable colored output")

    init = commands.add_parser("init", help="create .zurix/config.json and .zurix/rules.md")
    init.add_argument("args", nargs=argparse.REMAINDER)

    verify = commands.add_parser("verify", help="verify a signed audit entry or an exported audit log")
    verify.add_argument("path", nargs="?", help="audit.json (one entry) or log.jsonl / JSON array (a chain)")
    verify.add_argument("--key", help="public key hex (default: fetched from zurixai.com)")
    verify.add_argument("--no-color", action="store_true", help="disable colored output")

    commands.add_parser("tui", help="open the terminal dashboard")
    commands.add_parser("version", help="print the version")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _parser()
    ns = parser.parse_args(argv)

    if ns.command == "check":
        from zurixai.cli.check import cmd_check
        sys.exit(cmd_check(get_config(), ns.path, use_json=ns.json, list_checks=ns.list, no_color=ns.no_color))
    if ns.command == "init":
        from zurixai.cli.init import cmd_init
        cmd_init(get_config(), ns.args)
    elif ns.command == "verify":
        from zurixai.cli.verify import cmd_verify
        cmd_verify(([ns.path] if ns.path else []) + (["--key", ns.key] if ns.key else [])
                   + (["--no-color"] if ns.no_color else []))
    elif ns.command == "tui":
        from zurixai.tui.app import run_tui
        run_tui()
    elif ns.command == "version":
        print(f"zurixai {__version__}")
    else:
        parser.print_help()
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
