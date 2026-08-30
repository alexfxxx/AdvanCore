# TASK-167 — Fleet Controlled Activation

STATUS: COMPLETE

## Objective

Activate the approved TASK-166 Fleet hire-purchase extension against the saved
local PostgreSQL database only after the owner reviews the fresh-backup and
pre-migration evidence recorded here.

## Business context

TASK-166 added five nullable Fleet finance fields, read-time remaining-payment
calculations and browser-local detail-display controls. The source migration is
reviewed and merged, but the saved local database must remain unchanged until a
fresh verified backup exists and the owner separately approves activation.

## Facts

- PR #62 merged into `projects-lifecycle-recovery`, not `main`, on 30 August
  2026 as merge commit `638855f9098475d44ba7ea323a6a00f6d3cf75e1`.
- GitHub CI and GitGuardian passed before the merge; the TASK-166 Bugbot rerun
  had no unresolved findings.
- The source migration chain has one head: `f3e166fleet3`.
- The saved local database remains at `e2f119fleet2`, the direct parent of
  `f3e166fleet3`.
- A fresh PostgreSQL custom-format backup was created and verified before any
  migration command was run.
- The canonical loopback-only PostgreSQL container was used. The automatically
  restarted legacy container was stopped without deletion because both
  containers referenced the same saved volume.
- No real Fleet finance values were entered or imported.

## Fresh backup evidence

- Backup ID: `advancore-20260830T094858Z-a7f68d0d`
- Created at: `2026-08-30T09:48:58Z`
- Archive format: `postgresql-custom`
- Archive size: `48,266` bytes
- SHA-256:
  `70d6fecc2db7a50436b74826a16136b0df8545c58fd4124de44666f4f06318b4`
- Built-in create-and-verify result: passed.
- Separate latest-backup verification: passed.
- Independent archive SHA-256 comparison with the manifest: matched.
- Backup directory permission: owner-only `0700`.
- Archive and manifest permissions: owner-only `0600`.
- Backup artifacts remain outside Git tracking in the established ignored local
  backup directory.

## Pre-migration database evidence

- Alembic revision: `e2f119fleet2`.
- Vehicles: `27`.
- Registered legal entities: `3`.
- Projects: `4`.
- Knowledge items: `7`.
- Activity log events: `60`.
- TASK-166 Fleet columns present before activation: `0 of 5`.

These counts are verification baselines only. No business record contents were
read into this task record.

## In scope after separate owner approval

- Reverify that the fresh backup remains the latest valid local backup.
- Reverify the database is still at `e2f119fleet2` and the repository source
  head is still `f3e166fleet3`.
- Apply only the additive migration from `e2f119fleet2` to `f3e166fleet3`.
- Confirm all 27 existing vehicles remain present and the five nullable columns
  were added without populating finance values.
- Rebuild the local Docker application against the merged integration source.
- Smoke-test the Streamlit Fleet edit/detail surface.
- Visually test the decoupled Fleet detail controls, including show/hide,
  reordering, keyboard/touch alternatives, persistence and reset.
- Run the focused Fleet/API/frontend tests and a post-migration disposable
  recovery rehearsal.
- Produce a non-secret completion report.

## Out of scope

- Applying any migration before separate owner approval.
- Entering or importing real hire-purchase or other business data.
- Changing the approved Fleet schema or business rules.
- Restoring over the saved operational database.
- Deleting the legacy database container or saved volume.
- Deployment, billing, credential changes, `main`, or publication beyond the
  approved integration branch.

## Database impact

Pending owner approval, one already-reviewed additive migration would add five
nullable columns and three bounded check constraints to `vehicles`. It would
not populate or rewrite existing vehicle rows. No migration was applied while
preparing this evidence.

## Acceptance criteria

- [x] PR #62 is merged only into `projects-lifecycle-recovery`.
- [x] A fresh local backup is created and cryptographically verified.
- [x] The pre-migration revision, record-count baselines and absent-column
      baseline are recorded.
- [x] The database remains at `e2f119fleet2` while awaiting owner approval.
- [x] The owner explicitly approves applying migration `f3e166fleet3`.
- [x] The migration is applied once and reaches exactly `f3e166fleet3`.
- [x] Existing record counts and all 27 vehicles remain intact.
- [x] Docker is rebuilt and both Fleet interfaces pass functional and visual
      checks.
- [x] A disposable recovery rehearsal passes against a generated temporary
      database only.
- [x] Completion evidence is produced without secrets or real finance values.

## Test requirements

- Before activation, repeat backup verification and revision checks.
- After activation, inspect the revision and five expected columns using
  read-only queries.
- Compare post-migration record counts with the baselines above.
- Run focused model, migration, vehicle-service, Streamlit, API and frontend
  contract tests.
- Exercise show/hide, drag ordering, keyboard/touch movement, refresh
  persistence and reset in the local UI.
- Run the existing disposable recovery rehearsal, which may create and delete
  only its generated temporary database.

## Constraints

- `agent_runner` remains the authority boundary.
- Fail closed if the backup becomes invalid, the database revision changes,
  multiple migration heads appear, the expected container cannot be proven or
  record counts differ before activation.
- Do not display, store or commit database credentials.
- Do not run a downgrade or in-place restore.
- Do not merge or otherwise interact with `main`.
- Do not enter real finance data as part of activation testing.

## Owner decisions

None. The owner approved the bounded TASK-167 activation on 30 August 2026.

## Completion report

### Implemented

- Merged the reviewed TASK-164 through TASK-166 work into the approved
  integration branch.
- Created and independently verified the fresh local backup.
- Captured the pre-migration revision, record-count and schema baselines.
- Reverified every activation prerequisite immediately before migration.
- Applied only additive migration `f3e166fleet3`.
- Recreated the canonical PostgreSQL Docker container while retaining its
  external saved-data volume; the verified legacy container stayed stopped.
- Launched the decoupled FastAPI console and Streamlit transition app from the
  merged integration source on loopback ports 8000 and 8501.
- Completed focused automated, functional, visual and recovery checks.

### Files changed

- `tasks/TASK-167-fleet-controlled-activation.md`

### Database changes

The approved additive migration advanced the saved database from
`e2f119fleet2` to `f3e166fleet3`. It added five nullable Fleet columns and
three bounded check constraints. All 27 vehicle rows remain, and all five new
values remain null because no real finance data was entered.

### Tests and results

- Backup create-and-verify: passed.
- Latest-backup re-verification: passed.
- Independent SHA-256 comparison: passed.
- Source migration head check: one head, `f3e166fleet3`.
- Pre-activation read-only database check: `e2f119fleet2`, 27 vehicles, no
  TASK-166 columns.
- Post-activation database check: `f3e166fleet3`, 27 vehicles, five nullable
  columns, three expected constraints and zero populated finance records.
- Focused model, migration, service, Streamlit, API and frontend tests:
  66 passed with one third-party Starlette deprecation warning.
- Local interface health check: FastAPI and Streamlit ready.
- Decoupled Fleet visual/function check: 27 vehicles displayed; owner/type/
  capacity controls rendered; Lorry filter returned only `GBJ3544B`; finance
  fields rendered truthfully as not recorded.
- Display-preference check: hide and keyboard reorder worked, persisted after
  refresh, and reset restored the approved defaults without changing data.
- Streamlit Fleet visual/function check: real Fleet table, record details and
  the five optional finance-edit fields rendered successfully.
- Disposable recovery rehearsal: passed against the fresh backup; four
  required tables verified and generated temporary database cleanup confirmed.
- Final read-only check: `f3e166fleet3`, 27 vehicles and zero generated recovery
  databases remaining.

### Assumptions

- The 27-vehicle count is the current owner-approved operational baseline.
- The canonical loopback-only local PostgreSQL container remains the approved
  local database runtime.

### Risks / unresolved issues

- The existing local Python environment required only the missing FastAPI and
  HTTPX packages and an in-range pytest version already declared in
  `requirements.txt`; those declared dependencies were repaired before local
  interface testing.
- Streamlit rewrote two repository skill symlinks while running from the shared
  environment. The generated links were quarantined under `/private/tmp`, and
  both tracked link targets were restored exactly; no application files were
  affected.
- Real hire-purchase values remain intentionally unpopulated until the owner
  supplies verified information.

### Decisions required

None for activation.

### Recommended next step

Commit and publish this completed TASK-167 evidence on its feature branch for
review into `projects-lifecycle-recovery`, not `main`. Then gather the owner's
exact business requirements before extending Fleet or starting another module.
