# TASK-052 — One-Command Local Startup

STATUS: REVIEW

## Objective

Provide one safe local command that checks prerequisites, starts PostgreSQL,
applies migrations and launches AdvanCore.

## In scope

- Add an owner-readable startup script and check-only mode.
- Reuse `.env.example`, Docker Compose, Alembic and Streamlit.
- Fail early without displaying connection strings or credentials.
- Document startup and shutdown.

## Out of scope

Production deployment, installing Docker/Python, production secrets, backup,
remote access, authentication, destructive database actions, or auto-upgrade.

## Allowed changed-file scope

- `tasks/TASK-052-one-command-local-startup.md`
- `scripts/start-advancore.sh`
- `README.md`
- `docs/runbooks/LOCAL_STARTUP.md`

## Owner decisions

None. This uses the existing documented local-development configuration.

## Completion report

### Implemented

- Added one command for prerequisite checks, local environment preparation,
  PostgreSQL startup, migrations and Streamlit launch.
- Added a no-change check-only mode and plain shutdown guidance.
- Repaired independent review by parsing rather than sourcing settings,
  rejecting symlinks/ambiguity/non-loopback database targets, and waiting up to
  30 seconds for PostgreSQL health before migrations.
- Repaired follow-up review by rejecting `.env` symlinks before fallback,
  creating missing settings with no-clobber semantics, clearing Compose/Docker
  routing variables, and fixing Compose to the repository file, local project,
  empty interpolation environment and default local Docker context.
- Added a bounded `--stop` mode that targets that exact same local Compose
  project and keeps the local database volume.

### Database changes

None in source. Startup applies already approved migrations to the local
development database.

### Tests executed and results

- POSIX shell syntax validation: passed.
- No-change check-only readiness validation: passed.
- Invalid-argument fail-closed check: passed with no mutation.
- `git diff --check`: passed.

### Decisions required

- Independent review and implementation approval remain manual.
