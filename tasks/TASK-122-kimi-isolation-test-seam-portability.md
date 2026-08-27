# TASK-122 — Kimi Isolation Test-Seam Portability Repair

STATUS: APPROVED

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

- [x] Registered production Kimi/Kimi-Swarm still requires the macOS sandbox
      and minimal environment.
- [x] An explicit custom executable test seam reaches the shared bounded runner
      on Linux without requiring `/usr/bin/sandbox-exec`.
- [x] Missing production isolation remains an eligible, fail-closed result.
- [ ] Focused tests, full tests and `git diff --check` pass. Focused tests and
      `git diff --check` pass; the full suite is blocked during collection by
      missing/incompatible host dependencies documented below.

## Owner decisions

- Approved as a bounded repair required to make the owner-approved TASK-121 PR
  pass CI without weakening production protections.

## Completion report

### Implemented

- Production `kimi` resolution continues through the macOS isolation
  preflight, sandbox wrapper and minimal Kimi environment.
- Explicit non-production executable overrides for Kimi and Kimi-Swarm now
  call the shared bounded runner directly with the configured timeout.
- Added focused coverage for the portable custom-executable seam and for
  fail-closed production isolation on both adapters.

### Files changed

- `advancore/agent_runner/worker.py`
- `tests/test_worker_timeout.py`
- `tests/test_worker_usage_guardrail.py`
- `tasks/TASK-122-kimi-isolation-test-seam-portability.md`

### Database changes

None.

### Tests executed and results

- `pytest -q tests/test_worker_timeout.py tests/test_worker_usage_guardrail.py`:
  23 passed.
- `git diff --check`: passed.
- `pytest -q`: blocked during collection with 31 pre-existing environment
  errors. The host lacks `streamlit` and `python-dotenv`, does not provide a
  usable Alembic installation, and has a SQLAlchemy version without
  `sqlalchemy.orm.mapped_column`. No repository-managed virtual environment is
  present, and dependency installation is outside this task's allowed scope.

### Assumptions

- ASSUMPTION: an adapter using the registered executable name `kimi`, including
  an explicitly supplied identical value, is production and must remain
  isolated; only a different explicit executable is the test seam.

### Risks / unresolved issues

- Full-suite verification remains unresolved until the approved project
  dependencies are available in the execution environment.

### Decisions required

None for implementation. Owner/reviewer approval remains required by policy.

### Recommended next step

Run the full suite in the project CI or an approved environment with the
requirements installed, then review the bounded diff. Do not commit until
explicitly approved.
