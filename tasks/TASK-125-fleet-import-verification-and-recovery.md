# TASK-125 — Fleet Import Verification and Recovery Evidence

STATUS: APPROVED

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
- Ignored local backup and recovery-evidence files.

## Database impact

Read-only checks against the live local database. The recovery rehearsal may
create and delete only its bounded disposable temporary database.

## Acceptance criteria

- [ ] Live counts and uniqueness match the approved batch.
- [ ] Every imported vehicle is linked to one of the three approved owners.
- [ ] Unknown finance, parking, insurance and ambiguous road-tax fields remain
      null.
- [ ] A post-import backup is verified and passes disposable recovery rehearsal.
- [ ] The Fleet page visibly shows the imported groups, filters and details.
- [ ] GitHub CI, secret scanning and independent review are clean before merge.

## Owner decisions

None. Corrections discovered during verification must stop for a new owner
decision rather than silently changing real operational data.

