# TASK-154 — Worker Efficiency Policy

STATUS: COMPLETE

## Objective

Stop routine development from spending more time troubleshooting AI providers
than implementing AdvanCore.

## Facts

- Kimi Swarm already has a governed eligibility gate for large multi-file work.
- TASK-153 remains isolated and pending an independent security review.
- The owner approved Gemini for normal bounded work and Codex as controller/fallback.

## In scope

- Document one-attempt, time-bounded Kimi usage and clear selection criteria.
- Keep Kimi opt-in for genuinely parallel work, not routine module development.
- Preserve existing authority, scope, integrity and fallback gates.

## Out of scope

- Provider installation, authentication, billing, live launches or TASK-153 code.

## Database impact

None.

## Allowed changed-file scope

- `docs/architecture/WORKER_EFFICIENCY_POLICY.md`
- `docs/runbooks/WORKER_ROUTING.md`
- This task file

## Acceptance criteria

- [x] Kimi selection and stop conditions are explicit.
- [x] Routine development can proceed without repeated provider troubleshooting.
- [x] Governance and unsafe-failure stops remain unchanged.

## Owner decisions

None. The owner approved the policy on 29 August 2026.

## Completion report

- Added a controller-owned worker efficiency policy and linked it from the routing runbook.
- Kimi Swarm is opt-in for genuinely parallel work; routine provider troubleshooting is time-bounded.
- No executable routing, credential, worker, database or publication behavior changed.
