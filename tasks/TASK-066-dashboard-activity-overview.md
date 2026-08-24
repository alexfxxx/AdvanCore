# TASK-066 — Dashboard Activity Overview

STATUS: REVIEW

## Objective

Add a small read-only dashboard overview of the existing approved Activity Log
so the owner can see whether lifecycle recording is operating.

## In scope

- Count total Activity Log records.
- Count Project, Knowledge, and other entity-type records.
- Display the four aggregate counts on the Dashboard.
- Use the existing repository/session boundary and generic failure handling.
- Add deterministic service and presentation coverage.

## Out of scope

Names, content, details, actors, IP/device data, credentials, charts, trends,
business KPI claims, mutation, deletion, export, retention, schema changes,
permissions, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-066-dashboard-activity-overview.md`
- `advancore/services/dashboard_service.py`
- `advancore/pages/dashboard.py`
- `tests/test_dashboard_service.py`
- `tests/test_dashboard_page.py`

## Owner decisions

The safe Activity Log policy and continuation through TASK-066 were approved
on 24 August 2026.

## Completion report

### Implemented

- Extended the read-only Dashboard summary with total, Project, Knowledge, and
  other activity counts.
- Injected ActivityLogRepository through the existing Dashboard database unit
  of work.
- Displayed the aggregate counts without names, content, details, or identity
  data.
- Added deterministic service and presentation coverage.

### Files changed

- `tasks/TASK-066-dashboard-activity-overview.md`
- `advancore/services/dashboard_service.py`
- `advancore/pages/dashboard.py`
- `tests/test_dashboard_service.py`
- `tests/test_dashboard_page.py`

### Database changes

None.

### Tests executed and results

- Focused Dashboard/Activity tests: 14 passed.
- Full repository suite: 903 passed.
- `git diff --check`: passed.
- Live Dashboard displayed 6 total activity events, split into 3 Project, 3
  Knowledge, and 0 other events.

### Assumptions

- Aggregate counts are sufficient for this first operational visibility slice;
  detailed inspection remains on the Activity Log page.

### Risks / unresolved issues

- Counts are loaded from the bounded local record set; pagination/large-volume
  aggregation is a future concern, not a current usability blocker.

### Decisions required

- Review, combined CI, and non-main integration remain governed follow-up
  actions.

### Recommended next step

- Publish the stacked TASK-062 through TASK-066 changes for independent review
  and integrate them into `projects-lifecycle-recovery` only if clean.
