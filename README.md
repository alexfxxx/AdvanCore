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
