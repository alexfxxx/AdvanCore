# TASK-090 — Platform Readiness Summary

STATUS: REVIEW

## Objective

Aggregate existing database, local-backup, and recovery-proof facts into one
bounded operator readiness summary.

## Business context

The app currently presents these facts separately. A provider-neutral summary
lets the Dashboard report local operating safety without showing configuration,
paths, credentials, raw errors, or invented business KPIs.

## In scope

- Define ready, attention, and unavailable display states.
- Aggregate the existing database probe, valid backup inventory, invalid-entry
  count, and latest-backup recovery match.
- Fail closed on source errors using fixed bounded messages.
- Add focused pure-service tests.

## Out of scope

UI changes, freshness thresholds, backup schedules, database mutation,
authentication, provider access, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-090-platform-readiness-summary.md`
- `advancore/services/platform_readiness_service.py`
- `tests/test_platform_readiness_service.py`

## Database impact

None; all inputs are existing read-only facts.

## Acceptance criteria

- [x] Database, backup, and recovery states remain separately visible.
- [x] Recovery is ready only when evidence matches the latest valid backup.
- [x] No unapproved age threshold is invented.
- [x] Provider errors become bounded unavailable states without details.
- [x] Focused tests and `git diff --check` pass.
- [x] Completion report produced.

## Constraints

This is local infrastructure readiness, not production readiness or a business
performance score.

## Owner decisions

None. Backup-age policy remains deferred.

## Completion report

### Implemented

Three-item local readiness aggregation with a fail-closed overall state.

### Files changed

Only the task, service, and focused tests.

### Database changes

None.

### Tests and results

Focused readiness tests and `git diff --check` pass.

### Assumptions

The first valid inventory record is the latest, as guaranteed by the backup
service.

### Risks / unresolved issues

No backup-age threshold is applied until the owner approves one.

### Decisions required

None.

### Recommended next step

Render the bounded summary on the Dashboard in TASK-091.
