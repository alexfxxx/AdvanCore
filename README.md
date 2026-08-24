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

- Streamlit user interface
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

4. Start AdvanCore:

   ```bash
   .venv/bin/streamlit run app.py
   ```

Open the local address printed by Streamlit. The Settings page shows whether
the database is configured and reachable without displaying its connection
details. When finished, stop the local database with `docker compose down`.

## Development Principles

1. Build the platform before adding complex modules.
2. Keep modules independent but connected through AdvanCore.
3. Approved knowledge must be controlled and traceable.
4. GitHub is the permanent source of truth for approved code and knowledge.
5. Human approval is required before draft knowledge becomes official.
6. Do not store passwords, API keys, credentials, or other secrets in GitHub.
7. Build only features that solve a defined business problem or support required platform infrastructure.

## Status

Gate 0 — Platform foundation setup.

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
- Select an item to view its read-only title, status, creation time, and content.

Editing, deletion, review/approval, search, project linking, source metadata,
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
