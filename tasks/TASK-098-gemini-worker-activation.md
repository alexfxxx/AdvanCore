# TASK-098 — Governed Gemini Worker Activation

STATUS: REVIEW

## Objective

Activate the already installed and owner-authenticated Antigravity CLI as a
bounded Gemini implementation worker while keeping `agent_runner` as the
authority boundary and preserving credential, repository, and approval gates.

## Business context

The owner has explicitly approved the continuous worker order
`Kimi → Gemini → Codex`. Gemini authentication and a synthetic smoke evaluation
were completed on 26 August 2026 without an API key or separately activated API
billing. This task establishes the safe worker adapter required before the
three-worker continuation route can be implemented in TASK-099.

## Facts

- The local `agy` CLI is installed and Google OAuth authentication succeeded.
- A synthetic response-only smoke test succeeded.
- The recorded smoke request used 31,142 tokens; this is not a remaining quota.
- Gemini is currently candidate-only and cannot be launched by `agent_runner`.
- The current production failover remains Kimi-Swarm to Codex until TASK-099.

## In scope

- Add Gemini to the fixed approved implementation-worker allowlist.
- Replace the disabled candidate adapter with a fixed Antigravity CLI adapter.
- Use code-owned non-interactive arguments, workspace sandboxing, bounded
  timeout, output format, and instruction scope.
- Pass only a minimal credential-free process environment; provider OAuth stays
  in the CLI's own account storage and is never copied into prompts or Git.
- Preserve the existing credential-input preflight and repository verification.
- Update worker registry, readiness, health, Dashboard/AI Center status, and
  runbook language to reflect owner-approved activation.
- Add deterministic tests that mock process launch; no real project prompt is
  sent to Gemini by the test suite.

## Out of scope

Automatic three-worker failover, planner/reviewer authority, API keys, billing,
model selection, arbitrary agent/command flags, browser scraping, credentials
inherited from the controller, production data, database changes, deployment,
or merge to `main`.

## Allowed changed-file scope

- `tasks/TASK-098-gemini-worker-activation.md`
- `advancore/agent_runner/worker.py`
- `advancore/agent_runner/worker_registry.py`
- `advancore/agent_runner/worker_rehearsal.py`
- `advancore/agent_runner/__init__.py`
- `advancore/services/worker_health_service.py`
- `advancore/services/candidate_readiness_service.py`
- `advancore/services/ai_usage_dashboard_service.py`
- `advancore/pages/ai_center.py`
- `docs/runbooks/WORKER_ROUTING.md`
- `docs/validation/MULTI_WORKER_GOVERNANCE_REHEARSAL.md`
- `tests/test_gemini_worker_foundation.py`
- `tests/test_worker_registry.py`
- `tests/test_worker_health_service.py`
- `tests/test_worker_routing_evidence_service.py`
- `tests/test_candidate_readiness_service.py`
- `tests/test_ai_center_page.py`
- `tests/test_ai_usage_dashboard_service.py`
- `tests/test_dashboard_page.py`

## Database impact

None.

## Acceptance criteria

- [x] Gemini is approved only for bounded implementation and fallback roles.
- [x] The fixed adapter uses `agy` print mode, accept-edits mode, sandboxing,
      disabled slash expansion, JSON output, and a bounded timeout.
- [x] The adapter exposes no caller-controlled executable, model, agent, plugin,
      API key, billing, permission-bypass, or arbitrary command option.
- [x] Likely credential material is rejected before launch.
- [x] Controller credentials and control variables are not inherited.
- [x] Missing executable, authentication, quota, timeout, and unknown failures
      remain eligible only through existing classified governance.
- [x] Gemini is visibly owner-approved but exact Google Pro balance remains
      unavailable unless supported evidence exists.
- [x] Current Kimi-to-Codex runtime routing is unchanged until TASK-099.
- [x] Focused and full tests plus `git diff --check` pass.

## Owner decisions

Approved on 26 August 2026: activate Gemini through the authenticated local
Antigravity CLI and use the eventual order Kimi, then Gemini, then Codex. An
unreadable balance must not by itself stop the overall workflow; the controller
should continue to the next approved worker. Existing safety and owner approval
boundaries remain in force.

## Completion report

### Implemented

- Activated the fixed local Antigravity CLI as a Gemini implementation and
  fallback worker.
- Added fixed non-interactive print, accept-edits, sandbox, disabled slash
  expansion, JSON output, new-project, and bounded-timeout arguments.
- Added a minimal process environment that retains only the account home needed
  by the CLI's existing OAuth session, fixed runtime paths, temporary storage,
  and non-sensitive locale values.
- Kept Gemini outside planning and review authority and left live automatic
  routing unchanged for the separate TASK-099 continuation change.
- Updated AI Center, worker health/readiness, Dashboard roles, offline rehearsal,
  and runbooks to show the owner-approved activation truthfully.

### Files changed

Task record, worker adapter/registry/exports/rehearsal, AI usage and readiness
services, AI Center, routing documentation, and focused tests listed in the
allowed changed-file scope.

### Database and credentials

No database, migration, API key, billing, OAuth, model-selection, deployment,
or `main` change. No credential was read, copied, printed, stored in Git, or
sent in a prompt. The adapter relies on the CLI's already established OAuth
session through the owner's account home.

### Verification

- Focused activation and affected routing/UI tests: 67 passed.
- Full suite: 1,119 passed and 2 skipped.
- Python compilation and `git diff --check`: passed.
- No additional Gemini request was sent; the prior synthetic smoke evaluation
  remains the authentication/evaluation evidence and no extra allowance was
  consumed for this implementation.

### Assumptions and risks

- The Antigravity CLI continues to support the locally inspected fixed flags.
- Provider authentication and quota are checked by the actual CLI launch; an
  unreadable dashboard balance alone does not mark Gemini unavailable.
- TASK-098 creates the worker boundary but intentionally does not yet provide
  the requested three-worker runtime chain.

### Decisions required and next step

No additional account decision is required. Independently review TASK-098,
then implement TASK-099 to continue automatically through Kimi, Gemini, and
finally Codex after eligible clean provider failures.
