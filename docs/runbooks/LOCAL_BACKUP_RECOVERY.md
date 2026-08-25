# Local Backup and Recovery Runbook

## Purpose

Protect the local AdvanCore PostgreSQL records independently from the Docker
volume. GitHub protects the application code and governed specifications; it is
not an operational database backup.

## What TASK-077 provides

- Owner-triggered backup from **Settings**.
- A command-line backup path when the Streamlit page is unavailable.
- PostgreSQL custom-format archives created with no-owner/no-privilege intent.
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

## Fail-closed recovery boundary

TASK-077 deliberately provides **no restore button or restore command**. Do not
run `pg_restore --clean`, do not restore into the configured `advancore`
database, and do not replace or remove the saved Docker volume.

If recovery is needed:

1. Stop business changes and preserve the current volume and backup folder.
2. Verify the selected backup again.
3. Create a separately named disposable PostgreSQL recovery database under a
   separately approved rehearsal procedure.
4. Restore only into that disposable database. The approved command must use
   `pg_restore --no-owner --no-privileges`.
5. Check migrations and business record counts before any owner decision about
   production recovery.

The disposable restore and verification workflow is the recommended next task.
It must prove that the target is not the configured saved database before it
performs any mutation.

## Current limitations

- Backups remain on the same Mac, so they do not protect against total Mac or
  disk loss.
- No automatic schedule or retention deletion exists yet.
- PostgreSQL cluster-global roles and tablespaces are not included.
- No point-in-time/WAL recovery exists.
- Recovery is not proven until a disposable restore rehearsal passes.
