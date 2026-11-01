"""
AGGRIX Dead Letter Queue (DLQ) Management CLI.

Provides operational commands to inspect, replay, and retry failed outbox events
quarantined in `analytics_dead_letter_events`.

Usage:
    # Inspect quarantined dead-letter events:
    python -m app.cli.dlq inspect
    python -m app.cli.dlq inspect --all --tenant-id <tenant_uuid>

    # Replay a specific dead-letter event by event ID:
    python -m app.cli.dlq replay --event-id <event_uuid>

    # Replay all quarantined dead-letter events:
    python -m app.cli.dlq replay --all

    # Reset failure attempts so the background worker daemon retries them:
    python -m app.cli.dlq reset --event-id <event_uuid>
    python -m app.cli.dlq reset --all
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from typing import List, Optional, TextIO

from sqlalchemy.engine import Engine

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.analytics.worker import IncrementalAggregationWorker
from app.database.connection import create_database_engine, engine as default_engine


def parse_args(args: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse CLI options for DLQ commands."""
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.dlq",
        description="AGGRIX Dead Letter Queue (DLQ) Management CLI",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="DLQ subcommands", required=True)

    # Subcommand: inspect
    inspect_parser = subparsers.add_parser("inspect", help="Inspect dead-letter events")
    inspect_parser.add_argument(
        "--tenant-id",
        type=str,
        default=None,
        help="Filter events by tenant UUID",
    )
    inspect_parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Include transient failures where attempts < max_retries",
    )
    inspect_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum records to display (default: 50)",
    )

    # Subcommand: replay
    replay_parser = subparsers.add_parser("replay", help="Replay dead-letter events through worker")
    replay_parser.add_argument(
        "--event-id",
        type=str,
        default=None,
        help="UUID of the specific outbox event to replay",
    )
    replay_parser.add_argument(
        "--tenant-id",
        type=str,
        default=None,
        help="Replay all quarantined events for a specific tenant",
    )
    replay_parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Replay all quarantined dead-letter events",
    )

    # Subcommand: reset
    reset_parser = subparsers.add_parser("reset", help="Reset attempt counter so background daemon retries")
    reset_parser.add_argument(
        "--event-id",
        type=str,
        default=None,
        help="UUID of the specific outbox event to reset",
    )
    reset_parser.add_argument(
        "--tenant-id",
        type=str,
        default=None,
        help="Reset all quarantined events for a specific tenant",
    )
    reset_parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Reset all quarantined dead-letter events",
    )

    return parser.parse_args(args)


def run_inspect(
    worker: IncrementalAggregationWorker,
    engine: Engine,
    tenant_id: Optional[uuid.UUID],
    quarantined_only: bool,
    limit: int,
    out: TextIO,
) -> int:
    """Inspect and format dead-letter records."""
    with engine.connect() as conn:
        records = worker.get_dead_letter_events(
            conn=conn,
            tenant_id=tenant_id,
            quarantined_only=quarantined_only,
            limit=limit,
        )

    if not records:
        filter_msg = f" for tenant {tenant_id}" if tenant_id else ""
        out.write(f"No {'quarantined ' if quarantined_only else ''}dead-letter events found{filter_msg}.\n")
        return 0

    out.write("\n" + "=" * 100 + "\n")
    out.write(f"AGGRIX Dead Letter Queue (DLQ) — Total Found: {len(records)}\n")
    out.write("=" * 100 + "\n")
    out.write(f"{'Event ID':<38} {'Type':<18} {'Attempts':<10} {'Tenant ID':<38}\n")
    out.write("-" * 100 + "\n")

    for r in records:
        out.write(f"{str(r['event_id']):<38} {r['event_type']:<18} {r['attempts']:<10} {str(r['tenant_id']):<38}\n")
        out.write(f"  Error: {r['error_message']}\n")
        out.write(f"  Last Failed At: {r['last_failed_at']}\n")
        out.write("-" * 100 + "\n")

    return 0


def run_replay(
    worker: IncrementalAggregationWorker,
    engine: Engine,
    event_id: Optional[uuid.UUID],
    tenant_id: Optional[uuid.UUID],
    replay_all: bool,
    out: TextIO,
    err: TextIO,
) -> int:
    """Replay specific or batch dead-letter events."""
    if not event_id and not tenant_id and not replay_all:
        err.write("ERROR: Specify --event-id <uuid>, --tenant-id <uuid>, or --all to replay.\n")
        return 1

    with engine.connect() as conn:
        with conn.begin():
            if event_id:
                try:
                    success = worker.replay_dead_letter_event(conn, event_id)
                    if success:
                        out.write(f"SUCCESS: Event {event_id} replayed successfully and removed from DLQ.\n")
                        return 0
                    else:
                        out.write(f"SKIPPED: Event {event_id} already had a consumer receipt.\n")
                        return 0
                except Exception as exc:
                    err.write(f"FAILED: Event {event_id} replay failed: {exc}\n")
                    return 1

            # Batch replay
            success_count, failure_count, errors = worker.replay_dead_letter_batch(
                conn, tenant_id=tenant_id
            )
            out.write(
                f"\nReplay Batch Completed: {success_count} succeeded, {failure_count} failed.\n"
            )
            if errors:
                err.write("Replay Errors:\n")
                for e in errors:
                    err.write(f"  - {e}\n")
                return 1 if failure_count > 0 and success_count == 0 else 0

    return 0


def run_reset(
    worker: IncrementalAggregationWorker,
    engine: Engine,
    event_id: Optional[uuid.UUID],
    tenant_id: Optional[uuid.UUID],
    reset_all: bool,
    out: TextIO,
    err: TextIO,
) -> int:
    """Reset attempt counters for dead-letter events."""
    if not event_id and not tenant_id and not reset_all:
        err.write("ERROR: Specify --event-id <uuid>, --tenant-id <uuid>, or --all to reset.\n")
        return 1

    event_ids = [event_id] if event_id else None
    with engine.connect() as conn:
        with conn.begin():
            count = worker.reset_dead_letter_attempts(conn, event_ids=event_ids, tenant_id=tenant_id)
            out.write(f"SUCCESS: Reset attempt counters for {count} event(s).\n")
            out.write("The running worker daemon will re-poll and process them on its next cycle.\n")

    return 0


def main(
    argv: Optional[list[str]] = None,
    engine: Optional[Engine] = None,
    out: Optional[TextIO] = None,
    err: Optional[TextIO] = None,
) -> int:
    """Main CLI entrypoint for DLQ commands."""
    stdout = out or sys.stdout
    stderr = err or sys.stderr

    args = parse_args(argv)
    eng = engine or default_engine or create_database_engine()
    worker = IncrementalAggregationWorker(engine=eng)

    tenant_uuid = uuid.UUID(args.tenant_id) if getattr(args, "tenant_id", None) else None
    event_uuid = uuid.UUID(args.event_id) if getattr(args, "event_id", None) else None

    if args.subcommand == "inspect":
        quarantined_only = not args.all
        return run_inspect(
            worker=worker,
            engine=eng,
            tenant_id=tenant_uuid,
            quarantined_only=quarantined_only,
            limit=args.limit,
            out=stdout,
        )

    elif args.subcommand == "replay":
        return run_replay(
            worker=worker,
            engine=eng,
            event_id=event_uuid,
            tenant_id=tenant_uuid,
            replay_all=args.all,
            out=stdout,
            err=stderr,
        )

    elif args.subcommand == "reset":
        return run_reset(
            worker=worker,
            engine=eng,
            event_id=event_uuid,
            tenant_id=tenant_uuid,
            reset_all=args.all,
            out=stdout,
            err=stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
