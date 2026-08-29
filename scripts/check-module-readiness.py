#!/usr/bin/env python3
"""Read-only local module-foundation check."""

from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from advancore.services.module_readiness_service import check_module_foundation


def main() -> int:
    result = check_module_foundation(REPOSITORY_ROOT)
    for item in result.items:
        print(f"{item.key}: {'ready' if item.ready else 'unavailable'}")
    return 0 if result.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
