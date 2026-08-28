# TASK-143 — Governed Task Queue Foundation

STATUS: READY

## Objective

Create a controller-owned queue for already approved governed tasks so future
unattended work can be sequenced without accepting arbitrary commands or
bypassing `agent_runner`.

## Business context

The owner wants exception-based operation across several approved tasks. A queue
must describe work waiting for the controller, not become a second executor or
authority boundary.

## In scope

- Add a local queue service with bounded `QUEUED`, `RUNNING`, `COMPLETED` and
  `BLOCKED` states.
- Accept only canonical TASK identifiers, repository-relative governed task-file
  paths, registered worker names and safe timestamps/status metadata.
- Store the queue outside worker repositories with owner-only permissions,
  bounded records, atomic writes and deterministic FIFO ordering.
- Require explicit controller methods for enqueue, claim, complete and block;
  reject invalid transitions, duplicates, stale claims and malformed state.
- Store no prompt, task body, command, credential, worker output, business data
  or publication authority.
- Add deterministic tests and a short operations runbook.

## Out of scope

- Launching workers, choosing fallbacks, retries, approvals, Git operations,
  publication, merges or deployment.
- Dashboard/UI work, PostgreSQL, Alembic, migrations or real data.
- Arbitrary paths, commands, URLs, account identifiers or environment values.

## Allowed changed-file scope

- `tasks/TASK-143-governed-task-queue-foundation.md`
- `advancore/agent_runner/task_queue.py`
- `tests/test_task_queue.py`
- `docs/runbooks/GOVERNED_TASK_QUEUE.md`

## Database impact

None.

## Acceptance criteria

- [ ] Approved tasks can be queued and claimed in deterministic FIFO order.
- [ ] State transitions are explicit, valid and fail closed.
- [ ] Duplicate, malformed, stale or unsafe records cannot launch or authorize
      anything.
- [ ] Storage is bounded, atomic, owner-only and outside worker repositories.
- [ ] Focused tests, full tests and `git diff --check` pass.

## Owner decisions

Approved for unattended implementation on 28 August 2026. Gemini is the
assigned implementation worker; Codex remains controller and final fallback.
