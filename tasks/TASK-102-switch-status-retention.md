# TASK-102 — Switch Status Retention

STATUS: APPROVED

## Objective

Keep controller-owned automatic-worker switch evidence useful across app sessions without allowing stale or unbounded evidence to fill its protected file.

## Business context

TASK-101 added safe cross-session switch notifications. Without bounded retention, normal long-term use could eventually fill the protected evidence file and prevent new notifications. The owner approved continuing through TASK-111 under the established governance rules.

## Facts

- The fixed worker route remains Kimi-Swarm, Gemini, then Codex.
- The Dashboard shows no more than five genuine handoffs from the preceding seven days.
- Switch evidence is stored outside worker-writable repositories with owner-only permissions.
- No routing, approval, credential, billing, database, deployment, or `main` change is required.

## In scope

- Compact the protected projection during controller writes.
- Retain only well-formed records within seven days and cap retained records at 1,000.
- Keep the existing two-megabyte hard limit.
- Treat worker selection older than seven days as unknown.
- Add deterministic tests and update the status runbook.

## Explicitly out of scope

- Provider usage or balance collection.
- Worker routing or approval changes.
- Database storage or migrations.
- Credentials, billing, deployment, production, or `main`.

## Allowed changed-file scope

- `advancore/agent_runner/auto_pipeline.py`
- `advancore/services/worker_routing_evidence_service.py`
- `docs/runbooks/AI_USAGE_DASHBOARD.md`
- `tests/test_worker_fallback.py`
- `tests/test_worker_routing_evidence_service.py`
- `tasks/TASK-102-switch-status-retention.md`

## Database impact

None.

## Acceptance criteria

- Protected evidence is compacted before every append.
- Malformed and expired records are discarded.
- At most 1,000 records and two megabytes are retained.
- Expired worker selection is not presented as current.
- Existing ownership, permission, symlink, workspace, and payload checks remain fail closed.
- Focused and full tests pass; Bugbot reports no unresolved valid issue.

## Test requirements

- Test compaction of malformed, expired, and recent records.
- Test expired selected-worker handling.
- Run focused switching tests and the full suite.

## Constraints

- `agent_runner` remains the authority boundary.
- Workers cannot write or approve controller evidence.
- GitHub remains source of truth.
- No merge to `main`.

## Owner decisions

None. Covered by the owner's explicit approval to implement TASK-102 through TASK-111 under the predetermined standards.

## Completion report

### Implemented

- Added controller-write compaction for the protected switching projection.
- Retained only well-formed records inside the seven-day window, capped at
  1,000 records and the existing two-megabyte hard limit.
- Expired selected-worker evidence now produces neutral unknown status.

### Files changed

- `advancore/agent_runner/auto_pipeline.py`
- `advancore/services/worker_routing_evidence_service.py`
- `docs/runbooks/AI_USAGE_DASHBOARD.md`
- `tests/test_worker_fallback.py`
- `tests/test_worker_routing_evidence_service.py`
- `tasks/TASK-102-switch-status-retention.md`

### Database changes

None.

### Tests and results

- Focused switching tests: 37 passed.
- Full isolated suite: 1,134 passed and 2 PostgreSQL-only migration tests
  skipped.
- Final full isolated suite after Bugbot repairs: 1,134 passed and 2 skipped.
- Repository whitespace validation: passed.

### Assumptions

Seven-day retention is measured relative to each new controller receipt.

### Risks / unresolved issues

Bugbot's valid edge-case findings were repaired. The final rerun was clean.

### Decisions required

None.

### Recommended next step

Verify, independently review, and publish only to `projects-lifecycle-recovery`.
