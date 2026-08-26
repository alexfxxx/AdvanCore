# TASK-092 — Worker Routing Evidence Bridge

STATUS: REVIEW

## Objective

Translate provider-neutral worker health summaries into conservative governed
routing evidence without launching or probing a worker.

## Business context

TASK-082 selection accepts explicit evidence, while TASK-083 health presents
truthful status. The controller needs a narrow bridge so UI previews and future
orchestration cannot invent availability.

## In scope

- Map Kimi available, paused, stale, and unavailable states exactly.
- Treat Codex “checked at launch” as unavailable for pre-launch selection.
- Keep Gemini setup-required even if a caller supplies contradictory health.
- Convert health-source failures to bounded unavailable evidence.

## Out of scope

Executable/account probing, worker launch, fallback execution, Gemini
authentication or activation, credentials, database changes, deployment, or
`main`.

## Allowed changed-file scope

- `tasks/TASK-092-worker-routing-evidence-bridge.md`
- `advancore/services/worker_routing_evidence_service.py`
- `tests/test_worker_routing_evidence_service.py`

## Database impact

None.

## Acceptance criteria

- [x] Known health maps to explicit evidence conservatively.
- [x] Launch-time checks never become pre-launch availability.
- [x] Candidate registry policy overrides contradictory status.
- [x] Provider errors reveal no details and fail closed.
- [x] Focused tests and `git diff --check` pass.
- [x] Completion report produced.

## Constraints

This bridge cannot consume authority or start a worker process.

## Owner decisions

None.

## Completion report

### Implemented

Provider-neutral health-to-routing evidence translation.

### Files changed

Only the task, service, and focused tests.

### Database changes

None.

### Tests and results

Focused evidence, health, registry, and selection tests pass; `git diff --check`
passes.

### Assumptions

Codex availability remains a launch-bound check until a separately approved
non-probing source exists.

### Risks / unresolved issues

When Kimi is unavailable, a read-only preview cannot assert Codex availability.

### Decisions required

None.

### Recommended next step

Build a truthful read-only route preview in TASK-093.
