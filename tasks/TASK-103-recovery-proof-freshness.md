# TASK-103 — Recovery Proof Freshness

STATUS: APPROVED

## Objective

Make the app distinguish current disposable recovery proof from evidence that is missing, invalid, for an older backup, or more than 30 days old.

## Business context

A restore rehearsal proves one backup at one time. Presenting very old proof as current could give the owner false confidence, while requiring a live restore would be unsafe. This task adds truthful expiry wording without touching operational data.

## Facts

- Disposable recovery rehearsal and protected local evidence already exist.
- Recovery proof must match the latest valid backup.
- The operational database must never be selected as a rehearsal target.
- The owner approved TASK-103 through TASK-111 under existing governance.

## In scope

- Define a 30-day freshness window for recovery evidence.
- Treat future-dated or older evidence as not current.
- Show attention wording in platform readiness and Settings.
- Add deterministic tests.

## Explicitly out of scope

- Running a restore, modifying a backup, or modifying the live database.
- New database schema or persistence.
- Credentials, deployment, production, or `main`.

## Allowed changed-file scope

- `advancore/services/recovery_evidence_service.py`
- `advancore/services/platform_readiness_service.py`
- `advancore/pages/settings.py`
- `tests/test_recovery_evidence_service.py`
- `tests/test_platform_readiness_service.py`
- `tests/test_settings_page.py`
- `tasks/TASK-103-recovery-proof-freshness.md`

## Database impact

None.

## Acceptance criteria

- Evidence through 30 days old remains current when it matches the latest backup.
- Older and future-dated evidence is not presented as current.
- Missing, invalid, mismatched, and expired states remain distinct and truthful.
- No restore or database write occurs.
- Focused and full tests pass; Bugbot is clean.

## Test requirements

- Test the exact 30-day boundary, older evidence, and future evidence.
- Test platform readiness wording and level.
- Run focused recovery/readiness tests and full regression.

## Constraints

- Fail closed on malformed evidence.
- Never expose paths, credentials, raw database errors, or backup contents.
- GitHub remains source of truth; no merge to `main`.

## Owner decisions

None. Covered by the owner's explicit approval.

## Completion report

### Implemented

- Added a shared, fail-closed 30-day recovery-evidence freshness check.
- Platform readiness and Settings now identify expired proof without running a restore.

### Files changed

- `advancore/services/recovery_evidence_service.py`
- `advancore/services/platform_readiness_service.py`
- `advancore/pages/settings.py`
- `tests/test_recovery_evidence_service.py`
- `tests/test_platform_readiness_service.py`
- `tests/test_settings_page.py`
- `tasks/TASK-103-recovery-proof-freshness.md`

### Database changes

None.

### Tests and results

- Focused recovery, readiness, Settings, and Dashboard tests after repair: 39 passed.
- Full isolated suite: 1,137 passed and 2 PostgreSQL-only migration tests skipped.
- Repository whitespace validation: passed.

### Assumptions

Thirty days is a conservative local operating interval, not a legal or regulatory rule.

### Risks / unresolved issues

Bugbot's valid boundary and test-scope findings were repaired. Final rerun: clean.

### Decisions required

None.

### Recommended next step

Verify, independently review, and publish only to `projects-lifecycle-recovery`.
