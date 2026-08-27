# TASK-114 — Operational CSV Import Foundation

STATUS: READY

## Objective

Provide a safe, preview-only CSV setup path for vehicles, drivers, customers,
and routes so operators can prepare real master data without manually retyping
every record or allowing an upload to mutate the database.

## Business context

The operational registers are usable but empty and currently accept one record
at a time. A deterministic template and validation preview reduces setup effort
while keeping real-data publication behind later governed review and approval.

## Facts

- The owner approved unattended safe implementation of TASK-114 through
  TASK-118 on 27 August 2026.
- Vehicles, drivers, customers, and routes already have governed service-layer
  validation and database tables.
- Real personal and business data must not be imported during this task.

## In scope

- Add downloadable UTF-8 CSV templates for vehicles, drivers, customers, and
  routes.
- Add a standard-library-only parser that accepts one known dataset type,
  requires exact headers, limits bytes and rows, and produces a bounded
  preview with row-level validation messages.
- Validate only deterministic field shape and existing domain constraints.
- Add a Transport Operations Setup tab that previews uploaded CSV data and
  clearly states that preview never saves records.
- Keep uploaded content in memory only and never log or persist row values.
- Add focused service and presentation tests.

## Out of scope

- Database writes, staging tables, migrations, duplicate database checks, or
  approval/publication of imported records.
- Real personal or business data, sample people, or invented fleet records.
- AI interpretation, fuzzy matching, address enrichment, external APIs,
  credentials, billing, deployment, authentication, or `main`.

## Allowed changed-file scope

- `tasks/TASK-114-operational-csv-import-foundation.md`
- `advancore/services/operational_import_service.py`
- `advancore/pages/operations.py`
- `tests/test_operational_import_service.py`
- `tests/test_operations_page.py`

## Database impact

None. Uploaded content is previewed in memory and is never persisted.

## Acceptance criteria

- [ ] Each supported dataset has one stable downloadable CSV template.
- [ ] Unknown types, malformed UTF-8, wrong or duplicate headers, oversized
      files, excessive rows, and invalid field values fail closed.
- [ ] A valid file produces a bounded preview with no database mutation.
- [ ] The UI states that preview does not save records.
- [ ] No uploaded row content is written to logs, Git, or controller artifacts.
- [ ] Focused and full tests pass.
- [ ] Completion report is produced.

## Test requirements

- Deterministic parser tests for all four templates and fail-closed boundaries.
- Presentation tests for templates, empty upload state, and preview rendering.
- Full repository pytest and `git diff --check`.

## Constraints

- Read and obey `AGENTS.md`.
- `agent_runner` remains the execution authority.
- Kimi-Swarm is the preferred implementation worker, followed by Gemini and
  Codex only through approved failover.
- GitHub remains source of truth.
- No worker may stage, commit, push, merge, expose credentials, or change the
  allowed scope.

## Owner decisions

None. The owner explicitly approved this bounded task. Real data mapping and
publication remain later tasks.

## Completion report

### Implemented

Pending.

### Files changed

Pending.

### Database changes

None.

### Tests and results

Pending.

### Assumptions

CSV is the first portable intake format; spreadsheet-specific imports remain
outside this task.

### Risks / unresolved issues

Database duplicate detection and approved publication are intentionally
deferred to TASK-115 and TASK-116.

### Decisions required

None.

### Recommended next step

Implement TASK-115 import review and duplicate detection after this task is
independently reviewed and integrated into `projects-lifecycle-recovery`.
