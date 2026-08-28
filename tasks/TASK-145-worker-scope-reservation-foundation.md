# TASK-145 — Worker Scope Reservation Foundation

STATUS: COMPLETE

## Objective

Create a controller-owned reservation service that detects overlapping governed
changed-file scopes before separately assigned implementation tasks can run.

## Business context

The owner permits Kimi and Gemini to work on separate non-overlapping governed
tasks. The controller needs deterministic, cross-process evidence that two
active assignments cannot claim the same file. This service is a safety
foundation only and does not launch workers or grant authority.

## In scope

- Add an immutable reservation record and explicit reserve, release and list
  methods.
- Accept only canonical task IDs, registered worker names and exact safe
  repository-relative file paths.
- Reject exact overlaps, ancestor/descendant path overlaps, duplicate active
  tasks, malformed state and future-dated records.
- Store bounded state outside the repository with an owner-only no-follow lock,
  owner-only file permissions and atomic replacement.
- Expire stale reservations by marking them released, never by launching or
  retrying work.
- Add deterministic tests and an operations runbook.

## Out of scope

- Worker launch, routing, retries, task approval, queue integration, Git
  operations, publication, merge or deployment.
- Wildcards, directory-wide claims, arbitrary commands or URLs.
- PostgreSQL, Alembic, migrations, real data, credentials or provider billing.

## Allowed changed-file scope

- `tasks/TASK-145-worker-scope-reservation-foundation.md`
- `advancore/agent_runner/scope_reservations.py`
- `tests/test_scope_reservations.py`
- `docs/runbooks/WORKER_SCOPE_RESERVATIONS.md`

## Database impact

None.

## Acceptance criteria

- [x] Non-overlapping task scopes can be reserved independently.
- [x] Overlapping, duplicate, malformed or unsafe reservations fail closed.
- [x] State updates are bounded, atomic, owner-only and concurrency-safe.
- [x] The service cannot launch, approve, publish or merge work.
- [x] Focused tests, full tests and `git diff --check` pass.

## Owner decisions

Approved for unattended safe implementation on 28 August 2026. Kimi and Gemini
were attempted on earlier non-overlapping tasks; Codex is the approved final
fallback while those providers are unavailable or nonproductive.

## Completion report

### Implemented

- Added exact and ancestor/descendant changed-file overlap detection.
- Added a concurrency-safe, owner-only state file and no-follow lock outside the
  worker repository, with atomic replacement and bounded retention.
- Added explicit reserve/release operations and four-hour stale expiry that can
  never trigger execution or retry.
- Rejected symbolic-link scope aliases, overlapping active records injected
  into persisted state, and future-dated release timestamps.
- Bound lock, read and atomic-replacement operations to a verified owner-only
  directory descriptor and rejected backward reservation timestamps.
- Kept state paths lexical until descriptor binding and repeated no-follow
  scope-component validation inside the locked reservation transaction.
- Rejected blocking non-regular state files and noncanonical dot-segment scope
  aliases before reservation.
- Treated case-only path variants and verified hard-link identities as the same
  scope, preventing duplicate worker ownership on macOS.
- Rejected controller state paths containing dot segments before containment or
  permission handling.
- Documented the service's lack of approval, launch, Git, database, publication,
  merge and deployment authority.

### Worker routing evidence

- Kimi remained unavailable behind its protected workspace-trust boundary.
- Gemini had already produced three successful-but-empty attempts on TASK-143.
- Codex implemented TASK-145 as the approved final fallback without relaxing
  either provider boundary.

### Database changes

None.

### Verification

- Focused tests: 20 passed, including concurrent overlap contention.
- Full post-rebase suite: 1,329 passed, 2 skipped.
- `git diff --check`: passed.

### Decisions required

None for TASK-145.
