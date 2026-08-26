# TASK-086 — Recovery Evidence Receipt

STATUS: REVIEW

## Objective

Store one strict, credential-free local receipt proving the latest successful
disposable recovery rehearsal and confirmed cleanup.

## Business context

Recovery was proven in TASK-079, but the result existed only in terminal output.
The local app needs durable evidence it can later present without exposing a
database address, credential, subprocess output, or operational row counts.

## In scope

- Add a versioned recovery evidence record and local ignored state store.
- Store backup identity, completion time, migration head, required-table count,
  and confirmed cleanup only.
- Use strict fields, bounded values, atomic replacement, private permissions,
  and symlink rejection.
- Treat missing evidence as absent and malformed evidence as unsafe.

## Out of scope

Running a rehearsal, restoring any database, UI changes, scheduling, cloud
copies, authentication, credentials, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-086-recovery-evidence-receipt.md`
- `advancore/services/recovery_evidence_service.py`
- `tests/test_recovery_evidence_service.py`

## Database impact

None.

## Acceptance criteria

- [x] Receipt is bounded, versioned, credential-free, and ignored by Git.
- [x] Only confirmed cleanup can be recorded.
- [x] Missing evidence remains truthfully absent.
- [x] Malformed, future-dated, extra-field, and symlinked evidence fails closed.
- [x] Focused tests and `git diff --check` pass.
- [x] Completion report produced.

## Constraints

The receipt is local evidence, not authorization to restore a live database.

## Owner decisions

None.

## Completion report

### Implemented

Strict atomic local recovery receipt persistence and validation.

### Files changed

Only the three allowed files.

### Database changes

None.

### Tests and results

Focused receipt tests and `git diff --check` pass.

### Assumptions

The existing ignored `.agent_runner` directory remains the local controller
state boundary.

### Risks / unresolved issues

A receipt proves one past rehearsal only; it does not make later backups proven.

### Decisions required

None.

### Recommended next step

Wire receipt creation to successful cleanup in TASK-087.
