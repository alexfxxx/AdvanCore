# TASK-122 — Kimi Isolation Test-Seam Portability Repair

STATUS: READY

## Objective

Repair PR #45's Linux CI failure by preserving the existing explicit custom
Kimi executable test seam while continuing to require macOS filesystem
isolation for the registered production `kimi` executable.

## Facts

- PR #45 GitGuardian passed.
- GitHub Linux CI failed only
  `tests/test_worker_timeout.py::test_all_production_adapters_use_shared_runner`.
- The test injects `sys.executable` as an explicit Kimi executable and mocks the
  shared bounded process runner.
- TASK-121's new isolation preflight currently runs for that explicit seam, so
  Linux fails because `/usr/bin/sandbox-exec` is unavailable.
- Before TASK-121, explicit non-production executable overrides bypassed Kimi
  usage/isolation handling; registered production adapters remained protected.

## In scope

- Apply the Kimi isolation preflight, sandbox command wrapper and minimal Kimi
  environment only when the adapter uses the registered production executable.
- Preserve the explicit custom executable solely as an injectable deterministic
  test seam using the shared bounded process runner and configured timeout.
- Add or adjust focused tests proving production remains isolated and the
  explicit test seam remains portable.

## Out of scope

- Weakening production Kimi credential screening, filesystem isolation,
  timeout, allowed scope or fallback rules.
- Usage evidence, provider accounts, credentials, database, deployment,
  billing, Fleet data or `main` changes.

## Allowed changed-file scope

- `tasks/TASK-122-kimi-isolation-test-seam-portability.md`
- `advancore/agent_runner/worker.py`
- `tests/test_worker_timeout.py`
- `tests/test_worker_usage_guardrail.py`

## Database impact

None.

## Acceptance criteria

- [ ] Registered production Kimi/Kimi-Swarm still requires the macOS sandbox
      and minimal environment.
- [ ] An explicit custom executable test seam reaches the shared bounded runner
      on Linux without requiring `/usr/bin/sandbox-exec`.
- [ ] Missing production isolation remains an eligible, fail-closed result.
- [ ] Focused tests, full tests and `git diff --check` pass.

## Owner decisions

- Approved as a bounded repair required to make the owner-approved TASK-121 PR
  pass CI without weakening production protections.

## Completion report

Pending implementation.
