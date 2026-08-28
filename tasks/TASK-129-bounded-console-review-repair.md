# TASK-129 — Bounded Console Review Repair

STATUS: COMPLETE

## Objective
Repair only confirmed TASK-128 defects while preserving all TASK-127 controller and publication gates.

## In scope
- `advancore/api/**`, `frontend/**`, and focused tests/documentation.
- Minimal fixes directly supported by TASK-128 evidence.

## Out of scope
- New business fields, database writes, migrations, worker-policy changes, deployment, or `main`.

## Database impact
None.

## Acceptance criteria
- [x] Every confirmed finding is fixed or explicitly rejected with evidence.
- [x] Focused/full tests and `git diff --check` pass.
- [x] Completion report produced.

## Owner decisions
None for bounded repairs.

## Completion report
Removed the remote Tailwind executable and added a same-origin Content Security
Policy. Added a controller-owned persistent repository lock, non-daemon job
execution, and graceful FastAPI shutdown so an active governed worker cannot be
silently orphaned or duplicated after restart. Added safe discovery of a newly
created governed checkpoint so live polling exposes its run ID and intermediate
phase before the synchronous runner returns. No database, migration, worker
policy, publication, deployment, or `main` change occurred.

Verification on 28 August 2026: 41 focused tests passed; the complete suite
passed with 1,287 tests and 2 intentional skips; JavaScript and shell syntax
checks passed; `git diff --check` passed.

Post-rebase independent review found and repaired two additional bounded
defects: authority-bearing HTTP requests now require the actual ASGI peer IP to
be loopback before a session token is issued or a mutation is accepted, and
worker-thread registration/start is atomic with graceful shutdown. Regression
tests cover spoofed loopback headers and shutdown during delayed thread start.
Bugbot's repair review was clean. The current base's pre-existing suite passed
with 1,381 tests and 2 intentional skips; the complete dependency-installed
suite is delegated to the isolated GitHub PR runner because no local package
installation was authorized.
