# TASK-157 — Module Business Design Gate

STATUS: COMPLETE

## Objective

Require owner-approved facts, fields, references and calculations before a
business module can authorise schema or implementation work.

## In scope

- Add a reusable module brief template and deterministic completeness validator.
- Distinguish facts, proposals and owner decisions.
- Require explicit database and compliance impact statements.

## Out of scope

- Deciding module business rules or creating migrations.

## Database impact

None.

## Allowed changed-file scope

- `advancore/services/module_design_service.py`
- `advancore/agent_runner/validation.py`
- `advancore/agent_runner/runner.py`
- `advancore/agent_runner/goal_task.py`
- `tasks/MODULE_BRIEF_TEMPLATE.md`
- `docs/business-rules/README.md`
- `tests/test_module_design_service.py`
- `tests/test_agent_runner.py`
- `tests/test_goal_task.py`
- `tests/test_planner_fallback.py`
- This task file

## Acceptance criteria

- [x] Incomplete or placeholder briefs cannot be marked implementation-ready.
- [x] A complete brief produces bounded section-level evidence only.
- [x] The validator never writes tasks, code or database state.
- [x] `agent_runner` blocks post-programme module work without a validated brief.

## Owner decisions

None.

## Completion report

- Added a reusable owner-facing module brief and a dependency-light, read-only validator.
- Missing facts, sections, approvals, placeholders or owner decisions fail closed.
- No business rules, schema or implementation authority is inferred by the gate.
- `agent_runner` requires an explicit module/non-module classification from
  TASK-164 onward and validates approved business-module briefs before launch.
- Updated the existing planner-fallback proposal fixture for the required
  version-two module classification fields.
