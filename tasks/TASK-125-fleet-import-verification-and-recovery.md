# TASK-125 — Fleet Import Verification and Recovery Evidence

STATUS: COMPLETE

## Objective

Prove that the approved Fleet import is usable, recoverable and truthfully
presented without changing business rules or expanding the data collected.

## In scope

- Run deterministic post-import database checks for counts, uniqueness,
  registered-owner grouping, exact capacities and null unknown costs.
- Create and verify a fresh post-import local backup.
- Restore that backup only into the approved disposable recovery database and
  remove the disposable database after verification.
- Visually inspect the Fleet list, filters and selected-vehicle detail view.
- Record bounded completion evidence without committing real Fleet values.

## Out of scope

- In-place restore, destructive database actions, data correction, new Fleet
  fields, authentication, deployment, credentials, billing and `main`.

## Allowed changed-file scope

- `tasks/TASK-125-fleet-import-verification-and-recovery.md`
- `advancore/services/activity_service.py`
- `advancore/services/database.py`
- `tests/test_activity_service.py`
- `tests/test_vehicle_service.py`
- `tests/test_session.py`
- Ignored local backup and recovery-evidence files.

## Database impact

Read-only checks against the live local database. The recovery rehearsal may
create and delete only its bounded disposable temporary database.

## Acceptance criteria

- [x] Live counts and uniqueness match the approved batch.
- [x] Every imported vehicle is linked to one of the three approved owners.
- [x] Unknown finance, parking, insurance and ambiguous road-tax fields remain
      null.
- [x] A post-import backup is verified and passes disposable recovery rehearsal.
- [x] The Fleet page visibly shows the imported groups, filters and details.
- [x] GitHub CI, secret scanning and independent review are clean before merge.

## Owner decisions

None. Corrections discovered during verification must stop for a new owner
decision rather than silently changing real operational data.

## Completion report

- Implemented: verified aggregate live data, created a post-import recovery
  point, rehearsed its disposable restore, and visually exercised company
  filtering plus selected-vehicle detail rendering.
- Bounded repairs: approved `vehicle_details_updated` activity events were
  missing from the Activity Log allowlist, and committed ORM values expired
  before Streamlit could render them after session close. Added the missing
  bounded event and configured application/test session factories to retain
  committed scalar values for read-only rendering.
- Database changes: no additional business-data writes beyond TASK-124.
- Recovery evidence: backup `advancore-20260827T150935Z-190ba719` was created,
  verified, restored into the disposable recovery database and cleaned up.
- Focused tests: 55 passed after the rendering repair; the earlier activity and
  vehicle-service repair check passed 36 tests.
- Full isolated suite: 1,253 passed and 2 skipped.
- Independent review: the Bugbot rerun was clean after removing two trailing
  blank lines identified in the task specifications.
- Visual verification: Transport Operations loaded without the prior detached
  instance failure; Fleet showed real grouped records, company/type/capacity
  filters, source-backed details and truthful `Not recorded` costs.
- Privacy: verification evidence records only counts and backup identity, not
  the real Fleet row payload.
- Risks: none unresolved; exact-head GitHub CI and secret scanning must remain
  green at merge time.
- Decisions required: none.
- Recommended next step: merge PR #46 only into
  `projects-lifecycle-recovery` after exact-head GitHub gates are green.
