# TASK-151 — Governed Rework and Retry Lifecycle

STATUS: COMPLETE

## Objective

Add a bounded queue transition for independently reviewed worker output that
requires rework, so a controller can issue a fresh attempt without creating a
duplicate task record or bypassing task approval.

## Required implementation

- Extend `TaskQueueRecord` with a backward-compatible integer attempt counter.
- Increment the counter only when `claim_next` creates a new `RUNNING` attempt.
- Permit no more than three total attempts for one task.
- Add a controller-owned `requeue_for_rework(task_id, worker, now=...)` method.
- Requeue only an existing `RUNNING` or `BLOCKED` task whose governed task file
  has exactly `STATUS: REWORK`.
- Reject rework of a `COMPLETED` task; completion remains final.
- Requeue by updating the same task record, clearing claim/finish timestamps,
  assigning only an already approved worker name, and retaining its attempt
  count until the next claim.
- Preserve atomic locking, monotonic timestamp checks, old queue-file loading,
  duplicate prevention and fail-closed validation.
- Export no execution, fallback, approval, Git, publication or merge authority.
- Add tests for first claim, bounded retries, worker reassignment, READY versus
  REWORK enforcement, completed-task finality, stale/blocked recovery,
  malformed counters and backward-compatible records without the new field.
- Update the queue runbook with the controller review/rework sequence.

## Allowed changed-file scope

- `advancore/agent_runner/task_queue.py`
- `advancore/agent_runner/__init__.py`
- `tests/test_task_queue.py`
- `docs/runbooks/GOVERNED_TASK_QUEUE.md`

## Constraints

- No database, PostgreSQL, models or Alembic changes.
- No Docker, dependency, login, credential, billing or deployment changes.
- Do not launch a worker, choose a fallback, approve output, stage, commit,
  push, open a PR, merge or touch `main`.
- Fail closed on ambiguous task state, timestamps, counters or task files.

## Acceptance criteria

- [x] At most three attempts can be claimed for one governed task.
- [x] Rework requires an explicit `STATUS: REWORK` task specification.
- [x] Completed tasks cannot be reopened.
- [x] Existing queue files remain readable with attempt count zero.
- [x] Focused tests and final controller scope verification pass.

## Owner decisions

None. This is the bounded retry behavior approved for unattended TASK-151.

## Completion report

- Kimi Swarm v0.39.0 ran first for 1,202.497 seconds. Its result was correctly
  rejected because it created an unapproved 16 MB `.tmp-venv`; that directory
  was moved intact to `/private/tmp/AdvanCore-task151-kimi-tmp-venv-quarantine`
  rather than deleted.
- The four intended files were retained for controller review. Bugbot found two
  fail-closed defects; both received bounded controller repair and the final
  Bugbot review was clean.
- No Gemini or Codex implementation-worker fallback was launched.
- Focused queue, launch and reporting tests: 63 passed.
- Local dependency-independent regression suite: 1,436 passed, 2 skipped.
- `py_compile` and `git diff --check`: passed.
