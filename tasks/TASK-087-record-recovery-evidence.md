# TASK-087 — Record Successful Recovery Evidence

STATUS: REVIEW

## Objective

Record the TASK-086 local receipt only after a disposable recovery rehearsal
passes and exact cleanup is confirmed.

## Business context

Evidence must describe a completed safe operation, never an attempt that left
cleanup uncertain. The normal CLI should create the receipt automatically so
the owner no longer needs to preserve terminal output manually.

## In scope

- Inject the local evidence service into the disposable recovery boundary.
- Record bounded evidence after successful verification and cleanup only.
- Configure the existing CLI to use the default ignored evidence location.
- Fail with a bounded message if the rehearsal passed but evidence persistence
  failed.

## Out of scope

Running another real rehearsal, Settings UI, schedules, operational restore,
authentication, provider access, credentials, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-087-record-recovery-evidence.md`
- `advancore/services/disposable_recovery_service.py`
- `scripts/rehearse-advancore-recovery.py`
- `docs/runbooks/LOCAL_BACKUP_RECOVERY.md`
- `tests/test_disposable_recovery_service.py`
- `tests/test_disposable_recovery_cli.py`

## Database impact

No live database change. Future owner-triggered rehearsals retain TASK-079's
generated disposable create/drop boundary.

## Acceptance criteria

- [x] Success evidence is recorded only after `dropdb` cleanup succeeds.
- [x] Failed or cleanup-uncertain runs record no success evidence.
- [x] CLI uses the strict default local evidence service.
- [x] Persistence errors expose no internal or credential details.
- [x] Focused tests and `git diff --check` pass.
- [x] Completion report produced.

## Constraints

Operational restore remains unavailable.

## Owner decisions

None.

## Completion report

### Implemented

Post-cleanup evidence recording in the disposable rehearsal and its CLI.

### Files changed

Only the allowed task, service, CLI, runbook, and focused tests.

### Database changes

None during implementation or tests.

### Tests and results

Focused evidence, rehearsal, and CLI tests plus `git diff --check` pass.

### Assumptions

Local ignored controller state remains available to the CLI user.

### Risks / unresolved issues

The previously completed TASK-079 rehearsal predates automatic receipts; a new
owner-triggered rehearsal will be needed to create current UI-visible evidence.

### Decisions required

None.

### Recommended next step

Show the receipt truthfully in Settings in TASK-088.
