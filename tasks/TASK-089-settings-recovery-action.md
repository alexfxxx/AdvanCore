# TASK-089 — Settings Disposable Recovery Action

STATUS: REVIEW

## Objective

Let the local owner explicitly run the already-governed disposable recovery
rehearsal from Settings without copying a terminal command.

## Business context

Recovery proof should be operable from the app. The action must retain the
TASK-079 fixed generated target and exact cleanup boundary.

## In scope

- Add one clearly labelled Settings button that is disabled without a verified
  local backup.
- Run only after an explicit click, using the existing no-caller-target service.
- Show bounded success or failure and refresh the receipt status after success.
- Preserve all loopback, generated-name, no-owner/no-privilege, and cleanup
  enforcement in the existing service.

## Out of scope

Automatic execution, caller-supplied database names, in-place restore, backup
retention, authentication, credentials, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-089-settings-recovery-action.md`
- `advancore/pages/settings.py`
- `tests/test_settings_page.py`

## Database impact

No implementation-time or live database changes. When the owner later clicks,
only one generated disposable database may be created and removed.

## Acceptance criteria

- [x] No click means no rehearsal.
- [x] No valid backup disables the control.
- [x] The UI supplies no restore target or database command.
- [x] Success refreshes the evidence view; failure exposes no details.
- [x] Focused tests and `git diff --check` pass.
- [x] Completion report produced.

## Constraints

Operational restore remains unavailable and requires separate owner approval.

## Owner decisions

None for adding the control; the owner retains per-run intent by clicking it.

## Completion report

### Implemented

Explicit local Settings action for the fixed disposable recovery service.

### Files changed

Task record, Settings page, and focused UI tests.

### Database changes

None during implementation or tests.

### Tests and results

Settings, recovery, and backup tests plus `git diff --check` pass.

### Assumptions

The Settings user is the local owner in the current single-user phase.

### Risks / unresolved issues

The action can take several minutes and needs the local PostgreSQL container.

### Decisions required

None.

### Recommended next step

Aggregate backup, recovery, and database readiness in TASK-090.
