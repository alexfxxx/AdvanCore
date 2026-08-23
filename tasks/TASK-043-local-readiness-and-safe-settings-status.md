# TASK-043 — Local readiness and safe Settings status

STATUS: READY

## Objective

Make the current application easier to start and diagnose locally by documenting the supported startup path and replacing the Settings placeholder with a read-only, non-sensitive readiness summary.

## Business context

The core Projects, Knowledge Hub, Dashboard, and Activity Log slices are usable, but a local owner currently lacks a simple startup guide and cannot tell from Settings whether the database is configured and reachable. This creates avoidable setup friction without requiring editable settings or vendor integration.

## Facts

- The app uses Streamlit, PostgreSQL, Docker Compose, Alembic, and the `DATABASE_URL` environment variable.
- The existing Settings page is placeholder text.
- The database layer already provides a read-only connection probe.
- The repository has no tracked `.env.example` or concise local quick-start sequence.

## In scope

- Add a small injected readiness service that reports only whether database configuration exists and whether its read-only probe succeeds.
- Replace Settings placeholder content with application version and safe configured/available indicators plus concise local guidance.
- Add a tracked local-only `.env.example` matching the existing Docker Compose development database.
- Add a concise README quick start for environment creation, dependencies, PostgreSQL startup, migration, app startup, and shutdown.
- Add focused service/page tests and an in-process Settings smoke check.

## Explicitly out of scope

- Displaying, logging, returning, validating, or editing database URLs, passwords, tokens, credentials, environment values, or connection exceptions.
- Editable settings, production configuration, secret management, user accounts, permissions, authentication, deployment, cloud hosting, AI providers, or external integrations.
- Schema, migration, model, repository, operational-data, Docker topology, port, or dependency changes.
- Automatic package installation, Docker startup, database creation, migration, app process launch, push, merge, deployment, reset, or history rewrite.

## Allowed changed-file scope

- `tasks/TASK-043-local-readiness-and-safe-settings-status.md`
- `.env.example`
- `README.md`
- `advancore/pages/settings.py`
- `advancore/services/readiness_service.py`
- `tests/test_readiness_service.py`
- `tests/test_settings_page.py`

## Database impact

None. One existing read-only connection probe may run when Settings is opened.

## Safety requirements

- Never render or include the database URL or raw probe/import exception in UI output.
- Missing or invalid configuration must produce a safe unavailable status and setup guidance, not crash the page.
- The environment example must be clearly local-development-only and contain no real secret.

## Acceptance criteria

- Settings shows the application version without reading operational records.
- Settings distinguishes not configured, configured-and-available, and configured-but-unavailable states.
- Probe exceptions fail closed to unavailable without leaking details.
- README provides one ordered local quick-start path using existing repository tooling.
- No editable setting, secret exposure, schema, dependency, deployment, or integration behavior is added.
- Exact changed paths remain within scope.

## Test requirements

- Test all readiness-service states, including an exception containing sensitive-looking text.
- Test Settings rendering for configured, available, unavailable, and safe non-leak behavior.
- Run focused tests, full `tests/`, compile/import, Streamlit Settings smoke, diff/index/scope/new-file checks.

## Constraints

- Preserve existing database module and deployment assumptions.
- Keep readiness logic independent of Streamlit and inject the probe.
- Do not treat local readiness as production health monitoring.
- Prefer small reversible changes and stop for any production/credential need.
- Completion requires the AGENTS.md report.

## Owner decisions

None. The environment example mirrors the already committed local Docker Compose defaults only.

## Completion report

### Implemented

### Files changed

### Database changes

### Tests executed and results

### Assumptions

### Risks / unresolved issues

### Decisions required

### Recommended next step
