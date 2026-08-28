# TASK-139 — Worker Operations Timeline

STATUS: READY

## Objective

Persist a safe controller-owned timeline for each governed implementation-worker
attempt so the owner can see when Kimi, Gemini or Codex started, stopped, failed
or switched and how long the attempt ran.

## Business context

TASK-138 added bounded timing and failure metadata to in-memory worker results
and runner audit records. The owner now needs durable cross-session operational
evidence without unreliable provider-balance estimates or raw worker content.

## In scope

- Add a service that projects one bounded worker-attempt event into a
  controller-owned JSONL file outside the worker repository.
- Record only timestamp, task identifier, registered worker name, start/finish,
  elapsed seconds, success, exit code, terminal reason, failure class,
  executable-resolution source and runtime-path profile.
- Enforce approved worker names, bounded strings/numbers, seven-day retention,
  maximum record count, owner-only directory/file permissions and atomic writes.
- Reject or discard malformed, future-dated, oversized and secret-like records.
- Integrate projection after a runner execution result exists; projection failure
  must be visible but must not alter the primary runner outcome.
- Add deterministic tests and document the privacy and failure semantics.

## Out of scope

- Raw prompt, command, executable path, PATH, environment, stdout, stderr,
  transcript, credentials, account identifiers or business/customer data.
- Provider-balance or quota estimation.
- Dashboard/UI changes, task queues, worker selection or retries.
- PostgreSQL, Alembic, migrations, real data, deployment or `main`.

## Allowed changed-file scope

- `tasks/TASK-139-worker-operations-timeline.md`
- `advancore/services/worker_operations_service.py`
- `advancore/agent_runner/runner.py`
- `tests/test_worker_operations_service.py`
- `tests/test_agent_runner.py`
- `docs/runbooks/WORKER_ROUTING.md`

## Database impact

None.

## Acceptance criteria

- [ ] Successful and failed worker attempts create bounded timeline events.
- [ ] Events survive app sessions for seven days and compact safely.
- [ ] No raw worker content, secrets, environment values or repository paths are
      persisted.
- [ ] Missing/invalid state fails closed and cannot change the runner result.
- [ ] Focused tests, full tests and `git diff --check` pass.

## Owner decisions

Approved for unattended implementation on 28 August 2026. Kimi is the assigned
implementation worker; Codex remains controller and final fallback.
