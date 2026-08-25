#!/usr/bin/env python3
"""Local owner CLI for creating and verifying AdvanCore backups."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from advancore.services.local_backup_service import LocalBackupService


def _service_from_environment() -> LocalBackupService:
    load_dotenv(REPOSITORY_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL", "")
    configured_directory = os.getenv("ADVANCORE_BACKUP_DIR")
    backup_directory = Path(configured_directory) if configured_directory else None
    return LocalBackupService(REPOSITORY_ROOT, database_url, backup_directory)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or verify a local AdvanCore PostgreSQL backup."
    )
    parser.add_argument(
        "action",
        choices=("create", "verify-latest", "status"),
        help="Safe local backup action to perform.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    service_factory: Callable[[], LocalBackupService] = _service_from_environment,
) -> int:
    arguments = _parser().parse_args(argv)
    try:
        service = service_factory()
        if arguments.action == "create":
            record = service.create_backup()
            print(f"Local backup created and verified: {record.backup_id}")
        elif arguments.action == "verify-latest":
            record = service.verify_latest()
            print(f"Latest local backup verified: {record.backup_id}")
        else:
            inventory = service.get_inventory()
            if inventory.records:
                print(
                    "Local backups ready: "
                    f"{len(inventory.records)} valid, "
                    f"{inventory.invalid_entries} invalid or incomplete"
                )
            else:
                print(
                    "No valid local backup is available. "
                    f"Invalid or incomplete entries: {inventory.invalid_entries}"
                )
    except Exception:
        print("Local backup action could not be completed safely.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
