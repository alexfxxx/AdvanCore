# TASK-156 — Standard Module Registry

STATUS: COMPLETE

## Objective

Create one immutable code-owned catalog that future AdvanCore modules can join
without duplicating navigation and identity rules.

## In scope

- Define bounded module identifiers, labels, maturity and presentation surfaces.
- Register existing core and transport capabilities only.
- Make Streamlit navigation consume the registry.

## Out of scope

- Dynamic third-party code loading, database configuration, permissions or new modules.

## Database impact

None.

## Allowed changed-file scope

- `advancore/module_registry.py`
- `app.py`
- `tests/test_module_registry.py`
- This task file

## Acceptance criteria

- [x] Module identifiers and labels are unique and deterministic.
- [x] Unknown or malformed registry entries fail closed.
- [x] Existing Streamlit pages remain available.

## Owner decisions

None.

## Completion report

- Added an immutable, validated catalog for current core and transport presentation modules.
- Streamlit navigation now consumes that catalog while preserving every existing page renderer.
- Focused registry and navigation tests passed.
