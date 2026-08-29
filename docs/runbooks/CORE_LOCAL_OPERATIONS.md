# Core Local Operations

This is the short owner workflow for the local AdvanCore foundation. Commands
must be run from the repository root.

## Before module development

```bash
.venv/bin/python scripts/check-module-readiness.py
./scripts/start-advancore.sh --check-only
```

The first command checks only the code-owned module catalog, business brief gate
and preview-first import contracts. The second checks local runtime readiness.
Neither command repairs files, starts a worker, applies migrations or imports
data.

## Start and verify the local application

```bash
./scripts/start-advancore.sh
.venv/bin/python scripts/check-local-interfaces.py
```

Open `http://127.0.0.1:8000` for the decoupled console. Streamlit on
`http://127.0.0.1:8501` remains a transitional interface for workflows not yet
moved to the decoupled console.

An unavailable check means unavailable; it does not trigger automatic repair or
claim that the application is ready.

## Protect local data

Backup and recovery are separate owner actions:

```bash
.venv/bin/python scripts/backup-advancore.py create
.venv/bin/python scripts/backup-advancore.py verify-latest
.venv/bin/python scripts/rehearse-advancore-recovery.py
```

The recovery command may create and delete only its generated disposable test
database. It never restores over the configured operational database.

## Stop

```bash
./scripts/start-advancore.sh --stop
```

Stopping must not delete the database volume, backup files or application data.
