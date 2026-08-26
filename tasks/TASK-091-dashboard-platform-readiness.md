# TASK-091 — Dashboard Platform Readiness

STATUS: REVIEW

## Objective

Show the bounded TASK-090 database, backup, and recovery summary on the
customizable Dashboard platform card.

## Business context

The owner should see local protection gaps on the first page without navigating
to Settings or interpreting raw technical checks.

## In scope

- Build the summary from existing local read-only services.
- Show one overall state and three bounded detail lines.
- Keep infrastructure readiness separate from business KPIs and fuel data.
- Preserve hidden-module behavior and secret-safe errors.

## Out of scope

New probes, schedules, automatic recovery, database mutation, authentication,
provider access, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-091-dashboard-platform-readiness.md`
- `advancore/pages/dashboard.py`
- `tests/test_dashboard_page.py`

## Database impact

None; existing database connectivity and local filesystem facts are read only.

## Acceptance criteria

- [x] Platform card shows ready, attention, or unavailable truthfully.
- [x] Database, backup, and recovery details remain distinguishable.
- [x] No raw error, credential, URL, path, or invented KPI is displayed.
- [x] Existing customizable layout behavior remains unchanged.
- [x] Focused tests and `git diff --check` pass.
- [x] Completion report produced.

## Constraints

The summary is local infrastructure readiness only.

## Owner decisions

None.

## Completion report

### Implemented

Dashboard platform protection summary and expandable bounded details.

### Files changed

Task record, Dashboard page, and focused Dashboard tests.

### Database changes

None.

### Tests and results

Dashboard and readiness tests plus `git diff --check` pass.

### Assumptions

The existing database probe and backup services remain the source facts.

### Risks / unresolved issues

No age policy is applied to backups or recovery evidence.

### Decisions required

None.

### Recommended next step

Bridge worker health to routing evidence in TASK-092.
