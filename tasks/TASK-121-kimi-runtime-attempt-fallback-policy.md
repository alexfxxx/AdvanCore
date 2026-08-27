# TASK-121 — Kimi Runtime Attempt and Fallback Policy

STATUS: READY

## Objective

Remove the obsolete AdvanCore 20% weekly-usage pause from the implementation
worker launch path so governed unattended work attempts Kimi-Swarm first and,
only after an eligible executable, authentication, quota/limit, or provider
capacity failure, notifies the owner and continues to Gemini and then Codex.

## Business context

The owner no longer wants locally estimated, missing or stale provider-balance
evidence to prevent an approved worker attempt. The provider CLI is the
authoritative runtime source for authentication, quota and capacity failures.
Existing credential screening, OS isolation, bounded process lifetime,
repository integrity checks and controller authority must remain unchanged.

## Facts

- The approved fixed implementation route is Kimi-Swarm, Gemini, then Codex.
- The Kimi CLI is installed and authenticated, but the adapter still calls the
  legacy usage service before launch.
- Missing, stale or at-least-20% usage evidence can prevent Kimi from being
  attempted even though TASK-101 says unreadable balance evidence must not
  block launch or continuation.
- Runtime provider errors are already classified into bounded executable,
  authentication, quota/limit and capacity categories before fallback.
- Unknown failures, timeouts, cancellation, unsafe state and Git mutation must
  continue to stop rather than fall through to another worker.

## In scope

- Remove usage-percentage, stale-balance and local weekly-runtime accounting
  from the Kimi adapter's production launch gate.
- Preserve the existing macOS Kimi filesystem sandbox and normal runner-owned
  per-process timeout independently of the removed usage-service preflight.
- Treat Kimi, Gemini and Codex health as checked at launch rather than deriving
  Kimi route availability from legacy balance evidence.
- Preserve the exact Kimi-Swarm to Gemini to Codex route, eligible failure
  classification, integrity checks and bounded switch notifications.
- Add deterministic tests and update the worker-routing runbook.

## Out of scope

- Provider account scraping, quota estimation, balance display or billing.
- Credential, OAuth, model, CLI installation or provider-account changes.
- Changing worker order, adding a fourth worker, retry loops or continuing
  after unknown failures, timeout, cancellation or repository mutation.
- Weakening credential screening, OS sandboxing, allowed-file scope,
  `agent_runner` authority, review, publication, database or `main` protections.
- Fleet data import, database changes, migrations, deployment or production.
- Removing the legacy usage-evidence service; it simply must not gate the fixed
  unattended worker launch route.

## Allowed changed-file scope

- `tasks/TASK-121-kimi-runtime-attempt-fallback-policy.md`
- `advancore/agent_runner/worker.py`
- `advancore/agent_runner/auto_pipeline.py`
- `advancore/services/worker_health_service.py`
- `tests/test_agent_runner.py`
- `tests/test_auto_pipeline.py`
- `tests/test_worker_health_service.py`
- `tests/test_worker_usage_guardrail.py`
- `tests/test_worker_fallback_integration.py`
- `docs/runbooks/WORKER_ROUTING.md`

## Database impact

None.

## Acceptance criteria

- [ ] Missing, stale, 20%-plus or unreadable usage evidence does not prevent a
      governed Kimi/Kimi-Swarm process attempt.
- [ ] Kimi retains credential screening, filesystem isolation and the bounded
      runner timeout.
- [ ] Classified Kimi executable, authentication, quota/limit or capacity
      failure can notify and continue to Gemini, then Codex, subject to all
      existing authority and integrity checks.
- [ ] Unknown failures, timeout, cancellation, unsafe input and Git mutation
      still stop without further fallback.
- [ ] Health evidence does not mark Kimi paused because of usage evidence.
- [ ] No credentials, account data, operational data, database schema,
      deployment or `main` behavior changes.
- [ ] Focused tests, full tests and `git diff --check` pass.

## Test requirements

- Prove production Kimi does not call usage refresh, percentage or
  runtime-budget preflight before launch.
- Prove the Kimi command remains sandboxed and uses its configured timeout.
- Prove Kimi health is checked at launch despite legacy usage evidence.
- Preserve existing three-worker fallback and stop-condition tests.

## Constraints

- `agent_runner` remains the authority boundary and workers cannot approve
  their own work.
- GitHub remains source of truth; publication may target only
  `projects-lifecycle-recovery`, never `main`.
- Do not expose credentials or weaken environment/filesystem protections.
- Do not infer provider quota. Attempt the worker and classify only its bounded
  launch result.

## Owner decisions

- Approved on 27 August 2026: remove the outdated 20% Kimi pause and use the
  fixed attempt order Kimi-Swarm, Gemini, then Codex. Notify on actual eligible
  worker switches.

## Completion report

Pending implementation.
