# Primary Console Cutover

## Decision

FACT: `http://127.0.0.1:8000` is the main AdvanCore application and the normal
owner starting point. The historical `http://127.0.0.1:8501` address redirects
to that primary app. `http://127.0.0.1:8502` is the temporary admin/editing
interface, not a competing main app.

The two interfaces reuse the same Python services and PostgreSQL operational
database. Business rules must stay in services rather than being copied into
browser JavaScript or Streamlit pages. Transferring a form means adding a
governed FastAPI route and primary-console presentation over the existing
service; it does not mean creating a second database workflow.

## Available in the primary app

- Customizable overview segments, themes, motion setting and mobile switcher.
- Controller-mediated Owner Goal preview, launch, progress and exact existing
  owner checkpoints.
- Local database/controller readiness.
- Bounded Projects and Knowledge summaries plus reviewed, confirmed management
  through their existing services.
- Fleet totals, filters, bounded vehicle list, selected-vehicle details and
  confirmed company/vehicle administration through existing services.
- Minimal Driver, Customer and Route create/status workflows using only their
  already-approved fields and lifecycle values.
- Dated Trip create/status and one-record-per-trip Assignment create/release
  workflows using the existing lifecycle services.
- Immutable Fuel and Financial entry recording with their existing optional
  links and no inferred accounting treatment.
- Read-only Activity Log history without browser mutation authority.
- Dispatch headline counts and recorded conflicts.
- Recorded Fuel intelligence and dated gross market benchmark.

## Temporary Streamlit-only admin/editing inventory

- Activity Log: advanced entity/action filtering and individual detail
  inspection beyond the primary app's read-only history.
- Settings/recovery: backup inventory, create/verify backup and disposable
  recovery rehearsal.
- Transport setup: completed-vehicle CSV preview/import.
- Dashboard AI readiness: the start-of-day Kimi, Gemini and Codex
  authentication check, explicit login guidance and owner-triggered refresh.
- Dashboard AI workforce: most recently selected worker and the retained
  seven-day automatic worker-switch history with bounded failure reasons.
- AI Center attention inbox: owner decisions and controller investigations
  that still require attention outside the primary progress view.
- AI Center routing status: selected implementation worker and the supporting
  Kimi/Gemini/Codex routing evidence without launching a worker.
- AI Center governance self-check: the offline multi-worker rehearsal and its
  zero-worker-launch verification result.
- AI Center Gemini readiness: candidate activation state, next owner action
  and the bounded governance checklist.

## Recommended transfer order

1. Start-of-day authentication readiness, selected-worker status, automatic
   switch history and routing evidence.
2. AI attention inbox, offline governance self-check and Gemini readiness.
3. Activity Log advanced detail filters.
4. Backup/recovery controls last, retaining their stronger confirmations.

TASK-170 through TASK-179 completed the shared safe-editing boundary and the
Projects, Knowledge, Fleet, Driver, Customer, Route, Trip, Assignment, Fuel and
Finance transfers plus read-only Activity Log history. Each mutation requires
loopback origin, a process-local action token, strict confirmation and existing
service validation. No schema or business field was added.

Every transfer remains a separately reviewed task. Database migrations, new
business fields, destructive actions, authentication, deployment and `main`
remain outside this cutover.

## Retirement condition

The Streamlit interface on port 8502 may be stopped by default only after every
required inventory item has an equivalent verified primary-console workflow
and the owner explicitly approves retirement. Until then it remains available
but clearly secondary. Port 8501 stays as a compatibility redirect so old local
bookmarks lead to the primary app instead of the temporary interface.
