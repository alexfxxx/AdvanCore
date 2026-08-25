# TASK-077 — Local Backup and Recovery Foundation

STATUS: REVIEW

## Objective

Give the owner a safe, local, independently verifiable PostgreSQL backup path
for AdvanCore's saved operational data without introducing cloud storage or an
automatic destructive restore.

## Business context

The local PostgreSQL volume now contains real project, knowledge, approval, and
activity records. GitHub protects code and governed specifications but is not
an operational database backup. The owner approved this foundation after the
TASK-078 visual layer.

## Facts

- GitHub is the source of truth for code and governed specifications.
- PostgreSQL is the operational database and currently runs locally on this Mac.
- PostgreSQL's custom archive format can be inspected with `pg_restore --list`
  without restoring or changing a database.
- The repository currently has no operational backup service, backup status,
  manifest, checksum, or recovery runbook.
- Restoring over the saved database is destructive and is not authorised by
  this task.

## Approved safety policy

- Backups are local, manual, and owner-triggered in this foundation.
- Each backup is a PostgreSQL custom-format archive plus a strict non-secret
  manifest and SHA-256 checksum.
- Backup directories and files use owner-only permissions and reject symlinks.
- Database credentials are passed only through the child process environment,
  never command arguments, manifests, UI messages, logs, or Activity Log.
- A backup is reported successful only after its archive signature, checksum,
  and PostgreSQL table of contents verify.
- Verification is read-only. No restore command is exposed through the app.
- Restore/recovery rehearsal must target a separate disposable database in a
  later explicitly approved task; it must never overwrite the saved database.

## In scope

- Add a local backup service using the installed PostgreSQL `pg_dump` and
  `pg_restore` client tools.
- Restrict the first implementation to a PostgreSQL database on loopback.
- Write custom-format archives atomically under a configurable local backup
  directory, defaulting to ignored `data/backups/`.
- Write strict versioned manifests with backup ID, UTC time, application
  version, archive filename, size, format, and SHA-256 only.
- Verify archive path containment, regular-file status, size, signature,
  checksum, and `pg_restore --list` output without database mutation.
- List valid local backup records newest first and calculate bounded total size.
- Add simple Settings controls to create a backup and verify the latest backup,
  with generic failures that do not leak credentials or tool output.
- Add a small local command-line entry point for creation, latest verification,
  and status when the Streamlit UI is unavailable.
- Add a recovery runbook that clearly blocks in-place restore and explains the
  disposable-rehearsal next step.
- Add focused service, CLI, Settings, safety, and documentation tests.

## Out of scope

- Automatic schedules, retention deletion, cloud/off-device copies,
  encryption-key management, incremental/PITR/WAL backups, multi-database or
  cluster-global objects, production backup policy, alerts, or remote databases.
- Restore into any database, `pg_restore --clean`, database drop/create,
  overwrite, replacement of the Docker volume, deletion of backups, or recovery
  rehearsal against saved data.
- Storing credentials, connection URLs, database names, business contents, or
  subprocess error text in manifests, UI messages, logs, or Activity Log.
- Authentication, UniFace, AI worker changes, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-077-local-backup-recovery-foundation.md`
- `.gitignore`
- `README.md`
- `advancore/pages/settings.py`
- `advancore/services/local_backup_service.py`
- `scripts/backup-advancore.py`
- `docs/runbooks/LOCAL_BACKUP_RECOVERY.md`
- `tests/test_local_backup_service.py`
- `tests/test_local_backup_cli.py`
- `tests/test_settings_page.py`

## Database impact

None. Backup creation reads PostgreSQL consistently; verification reads only the
archive. This task does not change schema, rows, or the saved Docker volume.

## Acceptance criteria

- [x] Backup files and manifests are created atomically with owner-only
      permissions in a non-symlink directory.
- [x] Only loopback PostgreSQL configuration is accepted.
- [x] Credentials never appear in argv, manifest, UI, or errors.
- [x] Archives use PostgreSQL custom format; creation declares no-owner and
      no-privilege intent, and any future restore must independently enforce
      `pg_restore --no-owner --no-privileges`.
- [x] A completed backup passes signature, exact size, SHA-256, and
      `pg_restore --list` verification.
- [x] Partial, corrupt, missing, symlinked, path-traversing, oversized, or
      unsupported manifests fail closed.
- [x] Settings can create and verify the latest backup with simple wording.
- [x] The CLI supports create, verify-latest, and status without printing
      credentials or raw tool failures.
- [x] No restore, deletion, remote copy, or background schedule is introduced.
- [x] Focused and full tests pass.
- [x] Completion report produced.

## Test requirements

- Unit-test URL validation, command construction, atomic creation, permissions,
  strict manifest parsing, signature/size/checksum checks, symlink/traversal
  rejection, generic failures, ordering, and empty state.
- Test Settings create/verify/status behavior and secret-safe failures.
- Test CLI exit codes and bounded output with an injected service.
- Run a real local backup and read-only verification against the existing local
  database without restoring it.
- Run focused tests, full repository tests, compilation, and `git diff --check`.

## Constraints

- Use argument-array subprocess calls without a shell.
- Never put a password or full database URL in argv or persisted metadata.
- Never reveal captured standard error to the UI or CLI.
- Preserve the saved PostgreSQL volume and every operational row.
- Preserve GitHub as source of truth and PostgreSQL as operational storage.
- Do not modify or merge to `main`.

## Owner decisions

The owner explicitly approved TASK-077 Local Backup and Recovery Foundation on
25 August 2026 after requesting the dashboard visual and voice layer. The owner
also removed UniFace from the roadmap.

## Completion report

### Implemented

- Added a loopback-only PostgreSQL custom-archive service using argument-array
  `pg_dump` and read-only `pg_restore --list` verification.
- Added atomic file replacement, file and directory synchronization, 0700/0600
  owner-only permissions, strict path/symlink boundaries, archive signature,
  exact-size, and SHA-256 verification.
- Added strict versioned manifests containing only bounded technical metadata;
  database URL, credentials, database name, business content, and raw tool
  errors are excluded.
- Added newest-first valid backup inventory with invalid/incomplete entry counts
  and local storage totals.
- Added Settings create/verify controls and status with generic safe failures
  and no restore capability.
- Added command-line create, verify-latest, and status actions for use when the
  Streamlit UI is unavailable.
- Added Git ignore protection, owner runbook, and README guidance.
- Created and independently verified the first real local backup.

### Files changed

- Task record, `.gitignore`, README, and local recovery runbook.
- New local backup service and command-line entry point.
- Settings backup status and owner-triggered controls.
- Focused service, CLI, safety, documentation, and Settings tests.

### Database changes

None.

### Tests and results

- Final focused backup/CLI/Settings suite: 27 passed.
- Final full repository suite: 1010 passed, 2 intentionally skipped in 167.02
  seconds.
- Compilation with an isolated bytecode cache and `git diff --check`: passed.
- Real local creation produced backup
  `advancore-20260825T161214Z-fe0f7a13`: 14,989-byte custom archive plus
  393-byte manifest, both mode 0600, followed by successful checksum and
  `pg_restore --list` verification.
- Post-backup read-only database check remained 4 projects, 7 knowledge items,
  6 activity events, and Alembic head `a94f8b17d6e2`.
- Live Settings inspection showed one valid 14.6 KB backup, both bounded owner
  controls, no raw configuration, and the no-restore warning.

### Assumptions

- The first bounded backup target is the current loopback PostgreSQL database.
- Local filesystem backups are a foundation, not sufficient protection against
  total Mac loss; an off-device policy requires a separate owner decision.

### Risks / unresolved issues

- A backup is not proven recoverable until it is restored into and checked in a
  separate disposable database.
- Local backups share the Mac's failure domain with the operational database.
- Files are protected by owner-only filesystem permissions but are not
  separately application-encrypted. Mac disk encryption, off-device copies,
  and backup-key policy remain separate decisions.

### Decisions required

None for this approved foundation.

### Recommended next step

Publish this branch for independent GitHub checks and integrate it into
`projects-lifecycle-recovery` when green. Then separately approve a disposable
recovery rehearsal that can never target the saved database.
