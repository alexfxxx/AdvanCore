# TASK-113 — Recovery Evidence Clock Repair

Status: APPROVED

## Goal

Allow a successful disposable recovery rehearsal to record its strict local receipt when the system clock includes microseconds, without weakening future-date rejection.

## Trigger

The owner-approved post-migration rehearsal restored and verified the backup and confirmed cleanup, but receipt recording failed because the validator compared a microsecond-bearing completion time with a truncated current time.

## Scope

- Compare the evidence timestamp with the actual timezone-aware current instant.
- Continue normalizing saved evidence to whole seconds.
- Add a regression test using a clock value with microseconds.

## Allowed files

- `advancore/services/recovery_evidence_service.py`
- `tests/test_recovery_evidence_service.py`
- `tasks/TASK-113-recovery-evidence-clock-repair.md`

## Excluded

- Database, backup, restore, migration, or cleanup boundary changes
- Credential, provider, deployment, or worker-routing changes
- Merge to `main`

## Acceptance criteria

1. A current clock value with microseconds records successfully.
2. A genuinely future-dated receipt still fails closed.
3. Existing receipt validation and disposable recovery tests pass.
4. Independent Bugbot review is clean before publication.

## Completion report

- Repaired the microsecond comparison without changing recovery boundaries.
- Focused recovery verification: 44 tests passed.
- Full verification: 1,179 tests passed and 2 PostgreSQL-only tests skipped under SQLite.
- Independent Bugbot review: clean.
