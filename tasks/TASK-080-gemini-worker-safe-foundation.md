# TASK-080 — Gemini Worker Safe Foundation

STATUS: REVIEW

## Objective

Represent Gemini as a disabled, code-owned candidate worker so future owner
authentication and evaluation can occur without granting execution authority
prematurely.

## Business context

The owner has Google AI Pro and wants Gemini available as another AI worker.
Account entitlement, authentication, CLI/SDK choice, API billing, and a real
AdvanCore smoke test are not yet confirmed and require the owner later.

## Facts

- `agent_runner` remains the permanent authority boundary.
- Kimi-Swarm is the current primary implementation worker and Codex is the
  approved fallback.
- No Gemini or Antigravity command is currently installed or authenticated in
  this workspace.
- The owner prohibited installation, login, API-key creation/transmission, and
  billing while unattended.

## In scope

- Add a fixed Gemini candidate adapter that never builds or launches a command.
- Return a bounded owner-action-required result for ordinary candidate runs.
- Apply the existing credential-input preflight before any candidate response.
- Add a separate candidate-only builder for deterministic simulation/tests.
- Keep Gemini outside every approved worker/planner allowlist and production
  route.
- Document the activation gates and add focused tests.

## Out of scope

- Installing or invoking Antigravity/Gemini, Google login/OAuth, API keys,
  billing, network calls, account probing, real prompts, repository writes by
  Gemini, worker approval, or route activation.

## Allowed changed-file scope

- `tasks/TASK-080-gemini-worker-safe-foundation.md`
- `advancore/agent_runner/worker.py`
- `advancore/agent_runner/__init__.py`
- `docs/runbooks/WORKER_ROUTING.md`
- `tests/test_gemini_worker_foundation.py`

## Database impact

None.

## Acceptance criteria

- [x] Gemini remains absent from approved worker and planner names.
- [x] The production adapter builder rejects Gemini.
- [x] The candidate builder accepts only the fixed Gemini candidate name.
- [x] Gemini candidate execution launches no process and requires owner action.
- [x] Likely credential material is blocked before the owner-action response.
- [x] No account, credential, billing, installation, or network operation is
      introduced.
- [x] Focused and relevant regression tests pass.
- [x] Completion report produced.

## Test requirements

- Test production rejection, candidate construction, no command, no process,
  credential blocking, and unknown candidate rejection.
- Run affected worker/routing/data-boundary tests and `git diff --check`.

## Constraints

- Preserve the established Kimi-Swarm to Codex unattended route exactly.
- Do not infer Gemini usage from the owner's Gemini app subscription.
- Do not modify or merge to `main`.

## Owner decisions

Google authentication, installation, API billing, provider surface, and real
activation remain owner decisions after TASK-080.

## Completion report

### Implemented

- Added a fixed Gemini candidate adapter with no executable, argv, endpoint, or
  authentication mechanism.
- Added a candidate-only builder that rejects every unregistered name.
- Preserved the production allowlists and Kimi-Swarm to Codex route unchanged.
- Applied the existing credential-material preflight before candidate results.

### Files changed

- Task record, worker boundary exports, routing runbook, and focused tests.

### Database changes

None.

### Tests and results

- Gemini foundation plus affected routing, fallback, and data-boundary tests:
  48 passed.
- `git diff --check`: passed.

### Assumptions

- Gemini remains useful as a future candidate even though its eventual Google
  surface and account entitlement are not yet selected.

### Risks / unresolved issues

- Gemini cannot perform real work until owner authentication, provider-surface
  selection, usage evaluation, and explicit activation are completed.

### Decisions required

- Later owner decision: authenticate and evaluate Google Antigravity or approve
  separately billed API access. No decision is required for this disabled
  foundation.

### Recommended next step

Proceed with TASK-081's vendor-neutral worker capability registry.
