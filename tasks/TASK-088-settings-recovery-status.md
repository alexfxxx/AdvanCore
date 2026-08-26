# TASK-088 — Settings Recovery Status

STATUS: REVIEW

## Objective

Show bounded recovery-rehearsal evidence in Settings and distinguish proof for
the latest valid backup from proof for an older backup.

## Business context

The owner should not need terminal history to know whether the current backup
has actually been restored successfully in a disposable database.

## In scope

- Read the strict local receipt without probing or changing a database.
- Show latest-backup proven, older-backup evidence, missing evidence, and
  invalid evidence as distinct states.
- Display only completion time, migration head, and required-table count.
- Replace the stale statement that recovery evidence is always absent.

## Out of scope

Running a rehearsal, restoring a live database, automatic schedules,
authentication, credentials, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-088-settings-recovery-status.md`
- `advancore/pages/settings.py`
- `tests/test_settings_page.py`

## Database impact

None; the Settings operation is read-only.

## Acceptance criteria

- [x] Latest and older backup evidence are not confused.
- [x] Missing evidence is not presented as failure or success.
- [x] Invalid evidence fails closed without details.
- [x] No credential, database address, file path, or row count is displayed.
- [x] Focused tests and `git diff --check` pass.
- [x] Completion report produced.

## Constraints

Recovery evidence never authorizes operational restore.

## Owner decisions

None.

## Completion report

### Implemented

Truthful recovery evidence states in the local Settings backup panel.

### Files changed

Task record, Settings page, and focused page tests.

### Database changes

None.

### Tests and results

Settings and evidence tests plus `git diff --check` pass.

### Assumptions

Backup identity is the safe join between the verified inventory and recovery
receipt.

### Risks / unresolved issues

The existing successful rehearsal has no receipt because it predates TASK-087.

### Decisions required

None.

### Recommended next step

Add an explicit owner-triggered disposable rehearsal control in TASK-089.
