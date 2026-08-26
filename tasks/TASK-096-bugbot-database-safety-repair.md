# TASK-096 — Bugbot Database Safety Repair

STATUS: REVIEW

## Objective

Resolve the three independent Bugbot findings from the TASK-086 through
TASK-095 review without widening authority or changing the live database.

## Business context

The reviewed batch adds recovery and worker-governance foundations. Independent
review found two database-safety edge cases and one persisted-state path edge
case that must be closed before a pull request is accepted.

## In scope

- Prove the exact canonical local PostgreSQL Compose project, service, image,
  data volume, and loopback port before backup or rehearsal commands run.
- Drop a disposable rehearsal database only after its creation was confirmed.
- Reject a symlinked failover state directory before path resolution.
- Add focused regression tests and clarify the recovery runbook.

## Out of scope

Live database changes, actual backup or recovery execution, container rebuild,
Docker installation, credential changes, worker activation, deployment, merge
to `main`, or any expansion of worker authority.

## Allowed changed-file scope

- `tasks/TASK-096-bugbot-database-safety-repair.md`
- `advancore/agent_runner/failover.py`
- `advancore/services/local_postgres_container_service.py`
- `advancore/services/local_backup_service.py`
- `advancore/services/disposable_recovery_service.py`
- `docs/runbooks/LOCAL_BACKUP_RECOVERY.md`
- `tests/test_local_postgres_container_service.py`
- `tests/test_local_backup_service.py`
- `tests/test_disposable_recovery_service.py`
- `tests/test_safe_failover.py`

## Database impact

None. Tests use fakes and temporary files. No database or container command is
executed by this task's verification.

## Acceptance criteria

- [x] Unrelated or ambiguously identified PostgreSQL containers fail closed.
- [x] The approved local database must use the expected project, service, image,
      volume, and loopback-only port binding.
- [x] Failed database creation never triggers a drop command.
- [x] Post-creation rehearsal failures still attempt exact bounded cleanup.
- [x] Symlinked failover state directories fail closed.
- [x] Focused and full tests pass.
- [x] One approved Bugbot re-review is completed cleanly.

## Owner decisions

The owner approved this repair cycle and one Bugbot re-review. Any additional
repair cycle or merge still requires a separate decision.

## Completion report

The three approved safety repairs are implemented. Focused verification passed
47 tests; the full suite passed 1,107 tests with 2 skips. The approved Bugbot
re-review confirmed all three findings are resolved and found no new actionable
correctness, security, or data-safety regression.
