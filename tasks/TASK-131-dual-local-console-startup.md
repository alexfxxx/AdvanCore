# TASK-131 — Dual Local Console Startup

STATUS: READY

## Objective
Start the FastAPI console on loopback alongside the existing Streamlit app without changing PostgreSQL or migrations.

## In scope
- Extend the existing local launcher with bounded FastAPI startup and cleanup.
- Keep Streamlit at `127.0.0.1:8501` and FastAPI at `127.0.0.1:8000`.
- Preserve `--check-only` and `--stop` safety behavior.

## Out of scope
- Remote binding, authentication, deployment, new containers, destructive volume actions, or schema changes.

## Database impact
None.

## Allowed changed-file scope
- `scripts/start-advancore.sh`
- `tests/test_start_script.py`
- `README.md`
- This task file

## Acceptance criteria
- [ ] Both interfaces start from one local command.
- [ ] FastAPI failure stops cleanly without deleting data.
- [ ] Existing launcher tests pass.

## Owner decisions
None; existing ports and loopback boundaries are retained.

## Completion report
Pending.
