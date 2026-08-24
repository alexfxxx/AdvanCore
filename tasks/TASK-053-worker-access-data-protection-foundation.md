# TASK-053 — Worker Access and Data-Protection Foundation

STATUS: REVIEW

## Objective

Prevent routine Kimi/Codex work from receiving likely credential material while
keeping normal repository implementation work available.

## In scope

- Preflight worker instructions and their directly referenced governed task.
- Fail closed on high-confidence credential material, unsafe task links,
  unreadable tasks, or oversized worker input.
- Deny Kimi file reads from common repository and account credential locations.
- Return only a controlled owner-review message, never the detected value.

## Out of scope

Granting credential access, production data, customer data, authentication,
user roles, backup policy, deployment, or replacing provider authentication.

## Allowed changed-file scope

- `advancore/agent_runner/worker.py`
- `tests/test_worker_data_boundary.py`
- `tasks/TASK-053-worker-access-data-protection-foundation.md`
- `docs/runbooks/WORKER_DATA_BOUNDARY.md`

## Owner decisions

None for the deny-by-default foundation. Any future credential capability must
be separately designed and explicitly approved.

## Completion report

### Implemented

- Added a high-confidence, value-safe worker input preflight.
- Applied it to Kimi, Kimi-Swarm, Codex implementation and Codex planning.
- Extended Kimi's operating-system sandbox to deny reads from common credential
  files and directories while retaining its own provider authentication path.

### Database changes

None.

### Tests executed and results

- Worker data-boundary and affected worker suites: 40 passed.
- `git diff --check`: passed.

### Decisions required

- Independent review and implementation approval remain manual.
