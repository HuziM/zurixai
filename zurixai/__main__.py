"""Entry point for python -m zurixai."""

from __future__ import annotations

import sys

from zurixai.cli.check import cmd_check
from zurixai.cli.init import cmd_init
from zurixai.config import get_config


def main() -> None:
    cfg = get_config()
    args = sys.argv[1:]

    if not args:
        print("Usage: zurix <command>")
        print("Commands: check, init, scan, tui, version")
        sys.exit(1)

    command = args[0]

    if command == "check":
        cmd_check(cfg, args[1:])
    elif command == "init":
        cmd_init(cfg, args[1:])
    elif command == "version":
        from zurixai import __version__
        print(f"zurixai {__version__}")
    elif command == "tui":
        from zurixai.tui.app import run_tui
        run_tui()
    else:
        print(f"Unknown command: {command}")
        print("Commands: check, init, scan, tui, version")
        sys.exit(1)


if __name__ == "__main__":
    main()
