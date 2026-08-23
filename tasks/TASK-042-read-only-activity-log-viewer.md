# TASK-042 — Read-only Activity Log viewer

STATUS: APPROVED

## Objective

Replace the Activity Log placeholder with a bounded read-only Streamlit viewer for existing activity_log records.

## Business context

AdvanCore already has an ActivityLog model and database table, but users cannot inspect existing records. A read-only list/detail slice improves visibility without defining which events must be recorded, introducing audit policy, or mutating data.

## Facts

- ActivityLog contains id, required action, optional entity_type/entity_id/details, and timestamps.
- No ActivityLog repository/service exists and the page is placeholder text.
- No event creation is authorized by this task.
- No schema/migration is required.

## In scope

- Add an injected ActivityLogRepository with identifier lookup and deterministic newest-first listing.
- Add an injected read-only ActivityLogService.
- Render native Streamlit empty state, deterministic selector, and selected read-only details for action, entity type/id, details, and timestamp.
- Display clear absent-value fallbacks and safe missing/load failures.
- Add focused repository/service/page tests and README documentation.

## Explicitly out of scope

- Creating, editing, deleting, pruning, exporting, ingesting, or automatically generating activity records.
- Defining audit-event requirements, retention, compliance, permissions, authentication, actors/users, IP/device data, severity, categories, search, filters, pagination, or links.
- Showing credentials, environment values, raw exceptions, SQL, secrets, tokens, or production-only metadata.
- Database schema/migration/index/seed changes, custom components, dependencies, main, deployment, production data, remote mutation, push, merge, reset, or history rewrite.
- Any new repository file except the task, repository, service, and two focused test files listed below.

## Allowed changed-file scope

- `tasks/TASK-042-read-only-activity-log-viewer.md`
- `advancore/pages/activity_log.py`
- `advancore/repositories/activity.py`
- `advancore/repositories/__init__.py`
- `advancore/services/activity_service.py`
- `tests/test_activity_service.py`
- `tests/test_activity_log_page.py`
- `tests/test_repositories.py`
- `README.md`

## Database impact

None. Read existing activity_logs rows only.

## Safety requirements

- Viewer is read-only and performs no activity mutation.
- Unexpected failures render one generic safe message without internal details.
- Existing governance gates remain authoritative; no publication during implementation/verification.

## Acceptance criteria

- Existing records are listed newest first and selectable.
- Selected details show action, entity type/id, details, and created timestamp with safe absent-value fallbacks.
- Empty and missing-record states are deterministic.
- Repository/load errors show no raw exception or sensitive/internal text and no false data.
- No event generation, mutation, audit policy, retention, permission, schema, integration, deployment, or sensitive-data behavior is added.
- Exact changed paths remain within scope.

## Test requirements

- Test repository add-independent get/list ordering using isolated SQLite by inserting model rows through the session only as fixtures.
- Test service list/get delegation.
- Test page empty, populated/detail, missing, and safe failure states.
- Run focused activity/repository tests and full `tests/` suite.
- Run compile/import, in-process Activity Log smoke, diff/index/scope/new-file checks.

## Constraints

- Preserve page → service → repository → session dependency direction.
- Service must not import Streamlit; page must not issue SQL or manage transactions.
- Do not infer audit/compliance/retention/access rules.
- Prefer small reversible changes and stop for schema/out-of-scope needs.
- Completion requires the AGENTS.md report.

## Owner decisions

None.

## Completion report

### Implemented

- Added a read-only repository and service for identifier lookup and deterministic newest-first activity listing.
- Replaced the Activity Log placeholder with empty, selectable detail, missing-record, and generic failure states.
- Displayed action, entity type/id, details, and created time with clear absent-value fallbacks.
- Added focused repository, service, and page coverage plus an in-process Streamlit smoke check.

### Files changed

- `tasks/TASK-042-read-only-activity-log-viewer.md`
- `advancore/pages/activity_log.py`
- `advancore/repositories/activity.py`
- `advancore/repositories/__init__.py`
- `advancore/services/activity_service.py`
- `tests/test_activity_service.py`
- `tests/test_activity_log_page.py`
- `tests/test_repositories.py`
- `README.md`

### Database changes

None. The implementation reads the existing `activity_logs` table only.

### Tests executed and results

- Focused activity and repository suite: 15 passed.
- Full project suite: 747 passed.
- Python compile/import checks: passed.
- `git diff --check`: passed.
- Streamlit AppTest Activity Log route with an isolated SQLite record: zero exceptions, errors, or warnings; detail view rendered.

### Assumptions

- Existing activity records are safe for the current local operator to view because authentication and permissions are explicitly outside this bounded task.
- Newest-first means descending `created_at`, with descending identifier as a deterministic tie-breaker.

### Risks / unresolved issues

- No records are generated by this task, so a fresh installation shows the intentional empty state until another governed feature records activity.
- Authentication, authorization, retention, and audit/compliance policy remain undefined and were not inferred.

### Decisions required

None for this bounded read-only slice.

### Recommended next step

Keep event-generation policy separate and owner-approved; continue with a small usability/readiness task that does not invent audit, AI-provider, or settings rules.
