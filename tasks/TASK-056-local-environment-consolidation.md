# TASK-056 — Local Environment Consolidation

STATUS: REVIEW

## Objective

Make the current one-command local startup safely adopt the existing legacy
AdvanCore PostgreSQL data without deleting it, while preventing container-name,
port, and duplicate-volume conflicts.

## In scope

- Preserve the existing `advancore_advancore_postgres_data` Docker volume.
- Recognise only the exact legacy AdvanCore PostgreSQL container shape and fail
  closed on any ambiguous or incompatible same-name container.
- Stop, but do not delete, a verified legacy database container before starting
  the canonical local Compose service against the same persistent volume.
- Roll back to the previously running legacy container if canonical startup
  fails.
- Bind the canonical development database to loopback only.
- Keep bounded check-only and stop behavior.
- Add focused automated coverage and owner-readable migration guidance.

## Out of scope

Deleting legacy containers, volumes, worktrees, branches, or source changes;
production deployment; production data migration; remote database access;
credential changes; application feature work; Kimi/Codex routing policy;
approval-boundary changes; merge to `main`.

## Allowed changed-file scope

- `tasks/TASK-056-local-environment-consolidation.md`
- `docker-compose.yml`
- `scripts/start-advancore.sh`
- `tests/test_local_startup_script.py`
- `README.md`
- `docs/runbooks/LOCAL_STARTUP.md`

## Owner decisions

None. The owner approved proceeding with the reviewed consolidation on
24 August 2026. Destructive cleanup remains a separate owner decision.

## Completion report

### Implemented

- Removed the fixed global database container name and moved the canonical
  service to a loopback-only port binding.
- Declared the existing legacy PostgreSQL volume as the canonical shared local
  data volume, with safe creation on fresh installations.
- Added exact legacy container identity validation, reversible stop behavior,
  and restart rollback when canonical Compose startup fails.
- Bound Streamlit to loopback only and documented the legacy adoption path.
- Added focused automated coverage for check-only behavior, exact identity
  rejection, live adoption order, rollback, fresh-volume creation, and Compose
  safety settings.

### Files changed

- `tasks/TASK-056-local-environment-consolidation.md`
- `docker-compose.yml`
- `scripts/start-advancore.sh`
- `tests/test_local_startup_script.py`
- `README.md`
- `docs/runbooks/LOCAL_STARTUP.md`

### Database changes

None planned. Existing approved migrations remain authoritative.

### Tests executed and results

- Focused local-startup tests: 7 passed.
- Full repository suite: 874 passed.
- POSIX shell syntax validation: passed.
- `git diff --check`: passed.
- Live Docker adoption: canonical container healthy on `127.0.0.1:5432`,
  original volume mounted, legacy container preserved and stopped.
- Live migration/data check: Alembic at `639d8b65223c`; one project and one
  knowledge item preserved.
- Live browser check: Dashboard loaded on `127.0.0.1:8501`, database connected,
  and preserved record counts rendered.

### Assumptions

- The exact legacy local volume name remains
  `advancore_advancore_postgres_data`.
- A verified stopped legacy container may remain as a reversible fallback.

### Risks / unresolved issues

- Empty duplicate volumes and obsolete worktrees are intentionally preserved
  until separately approved cleanup.
- The preserved legacy container and canonical container both reference the
  same volume and must not be run simultaneously. The startup script enforces
  that boundary for its managed path.

### Decisions required

- Independent review and feature-branch publication remain governed follow-up
  decisions. No merge to `main` is authorised.

### Recommended next step

- Independently review the scoped diff, then publish it to a feature branch if
  clean. Destructive cleanup remains separate.
