# TASK-047 — Kimi-First Authorized Worker Routing

STATUS: REVIEW

## Objective

Make Kimi-Swarm the first implementation worker and Codex the one-hop fallback
for unattended work, while enforcing usage, integrity and standing authority.

## In scope

- Add provider-neutral authority wrappers around registered worker adapters.
- Build one fixed route: Kimi-Swarm primary, Codex fallback.
- Consume routine worker authority at actual launch and approved-fallback
  authority only when the existing integrity-gated pipeline invokes fallback.
- Preserve TASK-044 Kimi budget checks and existing one-hop fallback rules.
- Add tests and documentation.

## Out of scope

Credentials, arbitrary worker names/commands, more than one fallback, approval,
merge, `main`, deployment, or weakening repository integrity checks.

## Allowed changed-file scope

- `tasks/TASK-047-kimi-first-authorized-worker-routing.md`
- `advancore/agent_runner/worker_routing.py`
- `advancore/agent_runner/worker.py`
- `advancore/agent_runner/__init__.py`
- `tests/test_worker_routing.py`
- `docs/runbooks/WORKER_ROUTING.md`

## Owner decisions

None. The owner explicitly selected Kimi first with Codex or another approved
worker as fallback, subject to the 20%/one-hour Kimi policy.

## Completion report

### Implemented

- Added authority-enforcing registered-worker wrappers.
- Added the fixed Kimi-Swarm primary and Codex one-hop fallback route.
- Consumed worker authority only at launch and fallback authority only when the
  existing integrity-gated pipeline actually invokes fallback.
- Preserved TASK-044 limits and passed no new credentials.
- Repaired independent review by giving governed Codex fallback a minimal fixed
  runtime environment rather than the controller's complete environment.

### Files changed

- `tasks/TASK-047-kimi-first-authorized-worker-routing.md`
- `advancore/agent_runner/worker_routing.py`
- `advancore/agent_runner/__init__.py`
- `tests/test_worker_routing.py`
- `docs/runbooks/WORKER_ROUTING.md`

### Database changes

None.

### Tests executed and results

- Focused routing, worker-isolation/fallback, unattended-review and
  standing-authority suites after repair: 50 passed.
- Python compile and `git diff --check`: passed.

### Decisions required

- Independent review and implementation approval remain manual.
