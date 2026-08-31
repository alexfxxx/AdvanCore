# AdvanCore

AdvanCore is the central business intelligence and operations platform for the Advan ecosystem.

## Current Version

AdvanCore Platform v0.1

## v0.1 Objective

Build the core platform foundation that future AdvanCore business modules can plug into.

Initial components:

- Executive Dashboard
- Knowledge Hub
- Projects
- AI Center
- Activity Log
- Settings
- Module framework

Future modules may include:

- PO Monitoring
- Transport ERP
- Fleet Intelligence
- Fuel Intelligence
- Transport Operations
- Financial Intelligence
- Customer and Contract Management

## Core Architecture

- FastAPI-served HTML/CSS/JavaScript primary interface
- Temporary Streamlit admin/editing interface while remaining forms transfer
- Python service layer
- PostgreSQL database
- Docker local environment
- GitHub version control and approved knowledge source

## Local quick start

These steps use the repository's existing local-development configuration. Do
not reuse the example database password in production.

1. Create and activate a Python virtual environment, then install dependencies:

   ```bash
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copy the local environment example and start PostgreSQL:

   ```bash
   cp .env.example .env
   docker compose up -d postgres
   ```

3. Apply the existing database migrations:

   ```bash
   .venv/bin/alembic upgrade head
   ```

4. Start the primary AdvanCore app and temporary admin/editing interface:

   ```bash
   ./scripts/start-advancore.sh
   ```

Open `http://127.0.0.1:8000` as the main AdvanCore app. Use
`http://127.0.0.1:8501` only for temporary admin/editing workflows that have not
yet transferred to the primary interface. The Settings page shows whether the
database is configured and reachable without displaying its connection
details. When finished, stop the local database with
`./scripts/start-advancore.sh --stop`.

After the one-time Python environment setup, the same local startup can be run
with `./scripts/start-advancore.sh`. Use `--check-only` to check readiness
without starting services.

## Local database backups

The Settings page can create and verify an owner-only local PostgreSQL backup.
Backups use PostgreSQL's custom archive format, a strict non-secret manifest,
and SHA-256 verification. They default to ignored `data/backups/` and never go
to GitHub. The same safe actions remain available if the UI is unavailable:

```bash
.venv/bin/python scripts/backup-advancore.py create
.venv/bin/python scripts/backup-advancore.py verify-latest
.venv/bin/python scripts/backup-advancore.py status
```

Backups are created with the matching PostgreSQL client from the already-running
local database container. A separately approved disposable recovery rehearsal
is available without any caller-supplied database target:

```bash
.venv/bin/python scripts/rehearse-advancore-recovery.py
```

This command creates and deletes only its generated temporary database. It does
not expose an in-place restore path. Never restore over the configured saved
database. See
[`docs/runbooks/LOCAL_BACKUP_RECOVERY.md`](docs/runbooks/LOCAL_BACKUP_RECOVERY.md)
for the fail-closed recovery boundary.

The launcher also recognises the verified legacy `advancore-postgres` local
container. It keeps the existing database volume, stops the legacy container
without deleting it, and starts the canonical loopback-only database service
against the same saved data. Both the app and database listen on this Mac only.
An ambiguous same-name container fails closed.

## Development Principles

1. Build the platform before adding complex modules.
2. Keep modules independent but connected through AdvanCore.
3. Approved knowledge must be controlled and traceable.
4. GitHub is the permanent source of truth for approved code and knowledge.
5. Human approval is required before draft knowledge becomes official.
6. Do not store passwords, API keys, credentials, or other secrets in GitHub.
7. Build only features that solve a defined business problem or support required platform infrastructure.

## Status

Local core-readiness programme. The foundation is suitable for governed,
module-by-module development; it is not a production deployment.

Before starting a module, run the read-only foundation check:

```bash
.venv/bin/python scripts/check-module-readiness.py
```

Every business module must then complete and obtain owner approval for
`tasks/MODULE_BRIEF_TEMPLATE.md` before schema or implementation work begins.
See `docs/runbooks/CORE_LOCAL_OPERATIONS.md` for the concise local workflow.

## Projects

The Projects page supports the first bounded project workflow:

- List existing projects in creation order.
- Create an active project with a required name and optional description.
- Select a project to view its name, description, and status.
- Edit an active project's name and optional description.
- Explicitly archive an active project and immediately refresh its read-only state.
- Keep archived projects visible and clearly labelled.

Project names use exact-match uniqueness. Names and descriptions are trimmed,
blank descriptions are stored as absent, and names are limited to 200
characters. Restoration, deletion, permissions, lifecycle history, search,
filtering, pagination, bulk actions, and project analytics are intentionally
deferred.

## Dashboard

The landing Dashboard provides a read-only overview of total, active,
archived, and other-status projects plus total, draft, and other-status
knowledge items. Business KPIs, trends, targets, charts, and row-level details
remain intentionally deferred.

## Knowledge Hub

The Knowledge Hub supports the first bounded draft workflow:

- Create a draft with a required title and content.
- List saved knowledge items in creation order.
- Select an item to view its title, status, creation time, and content.
- Edit a draft and immediately see its refreshed saved values.
- Explicitly archive a draft and keep it visible as a read-only record.

Deletion, review/approval, search, project linking, source metadata,
attachments, AI features, and permissions are intentionally deferred.

## Activity Log

The Activity Log page provides a newest-first, read-only list and detail view
for existing activity records. Event generation, audit policy, retention,
search, export, actors, permissions, and record mutation are intentionally
deferred.

## AI Center

AI Center shows the read-only owner exception inbox for governed automation.
An all-clear state means no owner decision or controller investigation is
waiting; the page never applies decisions or exposes raw worker evidence.

## Running tests

The project uses `pytest`. Run the test suite from the repository root with:

```bash
.venv/bin/python -m pytest tests/ -v
```

Tests are intentionally isolated: model tests inspect SQLAlchemy metadata without touching a database, and database service tests mock the engine so no real credentials or data are required.

## Database migrations

AdvanCore uses Alembic to version PostgreSQL schema changes. Configuration and workflow details are documented in [`docs/architecture/MIGRATIONS.md`](docs/architecture/MIGRATIONS.md).

Common commands:

```bash
# Create a migration after changing models
.venv/bin/alembic revision --autogenerate -m "describe the change"

# Apply migrations
.venv/bin/alembic upgrade head

# Check current revision
.venv/bin/alembic current
```

`DATABASE_URL` is read from the environment (and `.env` in development) so credentials are never committed.
