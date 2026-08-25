# Local Backup and Recovery Runbook

## Purpose

Protect the local AdvanCore PostgreSQL records independently from the Docker
volume. GitHub protects the application code and governed specifications; it is
not an operational database backup.

## What TASK-077 provides

- Owner-triggered backup from **Settings**.
- A command-line backup path when the Streamlit page is unavailable.
- PostgreSQL custom-format archives created by the already-running PostgreSQL
  container's server-matched client, with no-owner/no-privilege intent.
  Because archive restore controls are applied by `pg_restore`, any future
  disposable restore must also use `--no-owner --no-privileges`.
- A strict non-secret JSON manifest, file size, and SHA-256 checksum.
- Automatic read-only validation with `pg_restore --list` before success is
  reported.
- Owner-only permissions on the backup directory and files.

The custom archive format follows PostgreSQL's documented portable archive
mechanism: <https://www.postgresql.org/docs/current/app-pgdump.html>. Read-only
table-of-contents verification uses:
<https://www.postgresql.org/docs/current/app-pgrestore.html>.

## Create a backup

Preferred owner path:

1. Open **Settings**.
2. Find **Local backup and recovery readiness**.
3. Select **Create and verify local backup**.
4. Treat the backup as successful only when the page says it was both created
   and verified.

Command-line alternative from the repository root:

```bash
.venv/bin/python scripts/backup-advancore.py create
```

The default location is `data/backups/`, which Git ignores. To use a different
local folder, set an absolute or user-relative `ADVANCORE_BACKUP_DIR` in the
local environment before starting the app or command.

## Check backup status

Use Settings, or:

```bash
.venv/bin/python scripts/backup-advancore.py status
.venv/bin/python scripts/backup-advancore.py verify-latest
```

Verification checks the manifest, regular-file and path boundaries, PostgreSQL
archive signature, exact size, SHA-256, and readable archive table of contents.
It does not connect to, create, drop, clean, or change any database.

## Proven disposable recovery rehearsal

The application deliberately provides **no in-place restore button or
command**. Do not run `pg_restore --clean`, do not restore into the configured
`advancore` database, and do not replace or remove the saved Docker volume.

TASK-079 adds one bounded local rehearsal command:

```bash
.venv/bin/python scripts/rehearse-advancore-recovery.py
```

It accepts no database name or other argument. It verifies the latest archive,
resolves exactly one running local PostgreSQL Compose service, generates a
unique `advancore_recovery_` database name, restores with the matching
container client and `--no-owner --no-privileges --exit-on-error`, checks the
migration head and bounded row counts for required tables, and then drops only
the exact disposable database it generated. Every post-creation failure still
attempts that exact cleanup. An ambiguous container or unconfirmed cleanup
fails closed.

If an actual recovery is needed:

1. Stop business changes and preserve the current volume and backup folder.
2. Verify the selected backup again.
3. Run the bounded rehearsal above and require a cleanup-confirmed pass.
4. Preserve the resulting evidence for owner review.
5. Treat any proposal to replace or restore the operational database as a new,
   separately approved destructive recovery task.

## Current limitations

- Backups remain on the same Mac, so they do not protect against total Mac or
  disk loss.
- No automatic schedule or retention deletion exists yet.
- PostgreSQL cluster-global roles and tablespaces are not included.
- No point-in-time/WAL recovery exists.
- Disposable recovery has been proven locally, but no in-place operational
  restore has been authorised or automated.
