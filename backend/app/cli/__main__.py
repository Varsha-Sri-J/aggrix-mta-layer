"""
Main CLI entrypoint for AGGRIX management commands.

Usage:
    python -m app.cli init-admin [options]
    python -m app.cli --help
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.cli.dlq import main as dlq_main
from app.cli.init_admin import main as init_admin_main


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="AGGRIX Multi-Tenant Analytics Management CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # init-admin subcommand
    subparsers.add_parser(
        "init-admin",
        help="Initialize the first platform administrator account (one-time bootstrap)",
        add_help=False,  # Let init_admin handle its own help
    )

    # dlq subcommand
    subparsers.add_parser(
        "dlq",
        help="Inspect, replay, and reset dead-letter queue (DLQ) events",
        add_help=False,  # Let dlq handle its own help
    )

    args, unknown = parser.parse_known_args()

    if args.command == "init-admin":
        return init_admin_main(unknown)
    elif args.command == "dlq":
        return dlq_main(unknown)
    else:
        # Default behavior if run without subcommand: show help
        parser.print_help()
        return 0 if not args.command and not unknown else 1


if __name__ == "__main__":
    sys.exit(main())
