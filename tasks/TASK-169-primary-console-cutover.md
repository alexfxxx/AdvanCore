# TASK-169 — Primary Console Cutover

STATUS: COMPLETE

## Objective

Designate the FastAPI-served HTML/CSS/JavaScript interface on port 8000 as the
official main AdvanCore app, demote Streamlit on port 8501 to temporary
admin/editing support, and create a truthful inventory and transfer order for
the workflows that still depend on Streamlit.

## Owner decision

APPROVED: port 8000 is the main AdvanCore app. Port 8501 is not the main app and
must remain only as temporary support until its required forms transfer.

## In scope

- Primary/temporary role labels in the UI, API status, startup output, health
  checks and current documentation.
- Code-owned module presentation metadata and primary-console anchors.
- Static-asset version bump so browsers show the new identity immediately.
- A clearly labelled temporary admin/editing link from the primary app.
- Truthful inventory of remaining Streamlit-only workflows and transfer order.
- Focused contract tests, full isolated regression and Bugbot review.

## Out of scope

- Transferring the individual create/edit forms in this task.
- Removing or disabling Streamlit before equivalent workflows exist.
- Database models, migrations, operational-data changes or imports.
- Controller, `agent_runner`, worker routing, authentication, deployment or
  merge to `main`.

## Acceptance criteria

- [x] Port 8000 is labelled and documented as the primary/main app everywhere
  in the active startup and primary-console paths.
- [x] Port 8501 is labelled only as temporary admin/editing support.
- [x] The primary app provides an explicit secondary link without implying
  that Streamlit owns business logic or governance.
- [x] The status response provides code-owned primary and temporary roles.
- [x] Remaining Streamlit-only functions are inventoried and ordered for
  transfer without inventing module requirements.
- [x] No database, migration, controller or operational-data change occurs.
- [x] Focused tests, full isolated regression, browser verification and Bugbot
  are clean before publication.

## Allowed files

- Primary frontend labels and cache-version references.
- FastAPI status/app and module-presentation metadata.
- Local startup and health-check labels.
- Current README/spec/state and primary-console architecture documents.
- Focused contract tests and this task report.

## Completion report

### Implemented

- Designated the FastAPI HTML/CSS/JavaScript console on port 8000 as the
  primary local AdvanCore app in the UI, API status, startup output, health
  labels and active documentation.
- Reclassified port 8501 as temporary admin/editing support and added a clearly
  labelled secondary link from the primary app.
- Added code-owned primary-console anchors and presentation roles to the
  module catalogue without moving business logic into either presentation.
- Inventoried every remaining Streamlit-only edit, recovery, AI-readiness and
  worker-governance workflow and documented the bounded transfer order and
  explicit retirement condition.
- Repaired Bugbot's retirement-inventory finding by protecting start-of-day
  authentication checks, selected-worker status, seven-day switch history,
  routing evidence, attention inbox, offline governance rehearsal and Gemini
  readiness.

### Database changes

None. No model, Alembic migration, database write, data import or operational
record change was made.

### Tests and results

- JavaScript syntax and `git diff --check`: passed.
- Focused cutover/API/module/startup suite before review: 33 passed.
- Full isolated SQLite regression: 1,583 passed, 2 skipped.
- Live loopback browser verification: custom CSS rendered, ambient animation
  ran, the multi-column segment grid rendered, all 27 Fleet records loaded and
  the browser console reported no warnings or errors.
- Focused suite after the bounded documentation repair: 33 passed.
- Final Bugbot review: CLEAN.

### Risks / unresolved issues

- Streamlit must remain available as temporary support until every inventoried
  workflow has an equivalent verified primary-console implementation and the
  owner explicitly approves retirement.
- The current live port-8000 runtime will not show TASK-169 until the completed
  branch is separately approved for commit, publication, integration and local
  restart.
