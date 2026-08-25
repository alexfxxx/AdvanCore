#!/usr/bin/env python3
"""Owner-approved disposable local recovery rehearsal."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from advancore.services.disposable_recovery_service import DisposableRecoveryService
from advancore.services.local_backup_service import LocalBackupService


def _service_from_environment() -> DisposableRecoveryService:
    load_dotenv(REPOSITORY_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL", "")
    configured_directory = os.getenv("ADVANCORE_BACKUP_DIR")
    backup_directory = Path(configured_directory) if configured_directory else None
    backup_service = LocalBackupService(
        REPOSITORY_ROOT, database_url, backup_directory
    )
    return DisposableRecoveryService(
        REPOSITORY_ROOT, database_url, backup_service
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    service_factory: Callable[[], DisposableRecoveryService] = _service_from_environment,
) -> int:
    if list(argv or []):
        print("Recovery rehearsal accepts no arguments.", file=sys.stderr)
        return 2
    try:
        result = service_factory().rehearse_latest()
        print(
            "Disposable recovery rehearsal passed: "
            f"{result.backup_id}; {len(result.table_counts)} required tables; "
            "cleanup confirmed."
        )
    except Exception:
        print(
            "Disposable recovery rehearsal could not be completed safely.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
