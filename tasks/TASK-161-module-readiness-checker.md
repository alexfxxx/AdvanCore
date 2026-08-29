# TASK-161 — Module Readiness Checker

STATUS: COMPLETE

## Objective

Provide one repeatable, read-only check that confirms the reusable foundations
needed before starting a module implementation.

## In scope

- Validate the module catalog, brief template and import contracts.
- Return bounded pass/fail items and a non-zero CLI exit on failure.
- Add deterministic tests.

## Out of scope

- Database access, worker launch, file repair or external calls.

## Database impact

None.

## Allowed changed-file scope

- `advancore/services/module_readiness_service.py`
- `advancore/services/module_design_service.py`
- `scripts/check-module-readiness.py`
- `tests/test_module_readiness_service.py`
- This task file

## Acceptance criteria

- [x] The checker is read-only and dependency-light.
- [x] Missing or malformed foundations fail closed.
- [x] Output contains no paths, environment values or credentials.

## Owner decisions

None.

## Completion report

- Added a read-only CLI check for the module catalog, business brief and preview-first import contracts.
- The command returns a non-zero status when a foundation is unavailable and never repairs state.
- Focused tests passed and the command reported all three current foundations ready.
- Template readiness now requires the canonical module identifier placeholder and
  uses bounded, repository-bound, no-symlink file reading.
