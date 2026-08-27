# TASK-137 — Local UI Preferences

STATUS: COMPLETE

## Objective
Allow the owner to change colour scheme, button feel, and animation intensity without touching governance or the database.

## In scope
- A small preferences panel with approved theme, control-radius, and motion choices.
- Browser `localStorage` persistence with validation and safe defaults.
- Reduced-motion support and reset-to-default control.

## Out of scope
- User accounts, server-side preferences, database writes, arbitrary CSS/HTML input, remote themes, or plugins.

## Database impact
None.

## Allowed changed-file scope
- `frontend/**`
- `tests/test_frontend_preferences_contract.py`
- `docs/architecture/DECOUPLED_LOCAL_CONSOLE.md`
- This task file

## Acceptance criteria
- [x] Preferences survive a browser refresh on the same device.
- [x] Only fixed allow-listed values are applied.
- [x] Governance controls and readable contrast remain intact.
- [x] Tests and visual checks pass.

## Owner decisions
None; presentation-only customization was approved.

## Completion report
Added browser-local, allow-listed theme, panel-shape and motion preferences with
safe defaults and reset. No arbitrary CSS, server preference or database write
is accepted. Midnight, light-business and responsive mobile layouts were
visually verified on 28 August 2026.
