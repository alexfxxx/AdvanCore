# TASK-145 — Worker Scope Reservation Foundation

STATUS: APPROVED

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

- [ ] Non-overlapping task scopes can be reserved independently.
- [ ] Overlapping, duplicate, malformed or unsafe reservations fail closed.
- [ ] State updates are bounded, atomic, owner-only and concurrency-safe.
- [ ] The service cannot launch, approve, publish or merge work.
- [ ] Focused tests, full tests and `git diff --check` pass.

## Owner decisions

Approved for unattended safe implementation on 28 August 2026. Kimi and Gemini
were attempted on earlier non-overlapping tasks; Codex is the approved final
fallback while those providers are unavailable or nonproductive.
