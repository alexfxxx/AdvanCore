# TASK-079 — Disposable Recovery Rehearsal

STATUS: REVIEW

## Objective

Prove that the latest verified local AdvanCore backup can be restored and
inspected in a separate disposable PostgreSQL database without changing the
saved operational database.

## Business context

TASK-077 created and verified a PostgreSQL custom archive, but archive
verification alone does not prove recovery. The owner approved one bounded
rehearsal that may create and delete only its own temporary database.

## Facts

- PostgreSQL is the operational database.
- The latest local backup already passes signature, checksum, size, and
  `pg_restore --list` checks.
- The live database and Docker volume must not be changed.

## In scope

- Add a loopback-only disposable recovery service and local command.
- Generate a service-owned database name with the fixed
  `advancore_recovery_` prefix.
- Create the disposable database, restore the latest verified archive with
  owner/privilege restoration disabled, and inspect required tables, migration
  head, and bounded row counts.
- Drop only the exact database created by the same rehearsal, including after a
  restore or verification failure.
- Return a bounded, credential-free pass/fail result.
- Add a recovery runbook update and focused safety tests.

## Out of scope

- Restore into, rename, drop, clean, truncate, or otherwise modify the live
  database or Docker volume.
- Retaining the disposable database, changing backup files, schedules,
  retention, off-device copies, encryption, login, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-079-disposable-recovery-rehearsal.md`
- `advancore/services/disposable_recovery_service.py`
- `advancore/services/local_backup_service.py`
- `scripts/rehearse-advancore-recovery.py`
- `docs/runbooks/LOCAL_BACKUP_RECOVERY.md`
- `README.md`
- `tests/test_disposable_recovery_service.py`
- `tests/test_disposable_recovery_cli.py`
- `tests/test_local_backup_service.py`
- `tests/test_local_backup_cli.py`

## Database impact

One uniquely named disposable local database is created and dropped during the
rehearsal. The operational database has no schema or row changes.

## Acceptance criteria

- [x] Only loopback PostgreSQL configuration is accepted.
- [x] The target can never equal the configured operational database.
- [x] Restore uses the latest independently verified archive and disables
      ownership and privilege restoration.
- [x] Required tables, migration head, and bounded row counts are checked.
- [x] Cleanup attempts only the exact service-created disposable database.
- [x] Credentials and raw subprocess output are never returned or persisted.
- [x] Failure paths still attempt safe cleanup and fail closed if cleanup is
      not proven.
- [x] Focused and full tests pass.
- [x] Completion report produced.

## Test requirements

- Test URL, identifier, command, restore, verification, and cleanup boundaries.
- Test failures before and after database creation.
- Run one real rehearsal against the latest verified local backup.
- Run focused tests, full tests, compilation, and `git diff --check`.

## Constraints

- Use fixed argument-array commands without a shell.
- Use the already-running PostgreSQL container's matching client tools for
  archive creation and restore; do not install another PostgreSQL version.
- Put credentials only in child-process environment variables.
- Do not print the configured database URL, password, or raw tool errors.
- Never use `pg_restore --clean` or `dropdb` for a caller-supplied name.
- Do not modify or merge to `main`.

## Owner decisions

The owner approved TASK-079 on 26 August 2026 and authorised creation and
deletion only of the disposable temporary database.

## Completion report

### Implemented

- Added a loopback-only disposable recovery service and no-argument local CLI.
- Added fixed generated target names, server-matched container restore,
  required-table/migration verification, and exact finally-block cleanup.
- Repaired backup creation to use the already-running PostgreSQL container's
  matching client after the rehearsal exposed a PostgreSQL 18-client to
  PostgreSQL 16-server incompatibility.
- Created a new compatible custom archive and completed a real restore,
  verification, and cleanup pass.

### Files changed

- Task record, README, and local backup/recovery runbook.
- Local backup compatibility repair and disposable recovery service/CLI.
- Focused backup, recovery, CLI, credential-safety, and cleanup tests.

### Database changes

None to the operational database. Each real attempt created and dropped only a
unique `advancore_recovery_` disposable database.

### Tests and results

- Focused backup/recovery suite: 34 passed.
- Full repository suite: 1025 passed, 2 intentionally skipped in 154.78 seconds.
- Real compatible backup created and verified:
  `advancore-20260825T171430Z-620c9a08`.
- Real disposable recovery rehearsal: passed for four required tables with
  cleanup confirmed.
- `git diff --check`: passed.

### Assumptions

- Exactly one running Docker Compose service labelled `postgres` is the
  approved local PostgreSQL server for backup and disposable recovery.

### Risks / unresolved issues

- Backups remain on the same Mac and therefore do not protect against total
  device loss.
- An operational in-place restore remains deliberately unavailable and would
  require separate explicit owner approval.

### Decisions required

None for this approved rehearsal.

### Recommended next step

Proceed with TASK-080's disabled-by-default Gemini worker foundation without
authentication, installation, billing, or activation.
