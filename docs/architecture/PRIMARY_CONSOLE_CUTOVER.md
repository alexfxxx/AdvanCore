# Primary Console Cutover

## Decision

FACT: `http://127.0.0.1:8000` is the main AdvanCore application and the normal
owner starting point. `http://127.0.0.1:8501` is a temporary admin/editing
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
- Bounded read-only Projects and Knowledge summaries.
- Fleet totals, filters, bounded vehicle list and selected-vehicle details.
- Dispatch headline counts and recorded conflicts.
- Recorded Fuel intelligence and dated gross market benchmark.

## Temporary Streamlit-only admin/editing inventory

- Projects: create, edit and archive.
- Knowledge: create draft, edit, approve, archive and forward replacement.
- Activity Log: full entity/action filtering and detail inspection.
- Settings/recovery: backup inventory, create/verify backup and disposable
  recovery rehearsal.
- Transport setup: completed-vehicle CSV preview/import and company creation.
- Fleet administration: create vehicle, status change and detail/finance update.
- Drivers, customers and routes: create and status change.
- Trips and assignments: plan trip, update trip status, assign and release.
- Fuel and finance: record fuel entries and financial entries.
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

1. Shared primary-console form and confirmation pattern, anti-CSRF checks and
   bounded service-error handling.
2. Projects create/edit/archive.
3. Knowledge draft/edit/approve/archive/replacement.
4. Fleet company/vehicle create, status and owner-approved detail editing.
5. Drivers, customers and routes.
6. Trips, assignments, fuel and financial entry.
7. Start-of-day authentication readiness, selected-worker status, automatic
   switch history and routing evidence.
8. AI attention inbox, offline governance self-check and Gemini readiness.
9. Activity Log detail filters.
10. Backup/recovery controls last, retaining their stronger confirmations.

Every transfer remains a separately reviewed task. Database migrations, new
business fields, destructive actions, authentication, deployment and `main`
remain outside this cutover.

## Retirement condition

Port 8501 may be stopped by default only after every required inventory item
has an equivalent verified primary-console workflow and the owner explicitly
approves retirement. Until then it remains available but clearly secondary.
