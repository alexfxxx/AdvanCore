# TASK-162 — Local Core Operations

STATUS: COMPLETE

## Objective

Make the local operator workflow for starting and checking the core concise and
truthful before business modules are added.

## In scope

- Add the module-readiness check to documentation and local check-only guidance.
- Keep interface, backup and recovery checks separate and explicit.
- Add startup/runbook contract tests where needed.

## Out of scope

- Starting Docker during tests, restoring data, deployment or network exposure.

## Database impact

None.

## Allowed changed-file scope

- `README.md`
- `docs/runbooks/CORE_LOCAL_OPERATIONS.md`
- `tests/test_core_local_operations_docs.py`
- This task file

## Acceptance criteria

- [x] Owner has a short start/check/stop sequence.
- [x] Documentation never claims unavailable services are ready.
- [x] Recovery remains disposable-only and separately invoked.

## Owner decisions

None.

## Completion report

- Added a concise local check/start/interface/backup/recovery/stop runbook.
- README now points future module work through the readiness checker and approved brief gate.
- No service, Docker container, database, backup or recovery operation was started.
