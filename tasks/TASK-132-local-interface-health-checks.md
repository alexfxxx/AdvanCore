# TASK-132 — Local Interface Health Checks

STATUS: READY

## Objective
Provide bounded readiness checks for the FastAPI and Streamlit loopback interfaces.

## In scope
- Add a local, non-secret readiness script and deterministic tests.
- Report each interface as reachable/unreachable without dumping responses or environment values.
- Integrate readiness into launcher messaging.

## Out of scope
- Remote monitoring, credentials, telemetry, hosted services, or automatic repair.

## Database impact
None.

## Allowed changed-file scope
- `scripts/check-local-interfaces.py`
- `scripts/start-advancore.sh`
- `tests/test_local_interface_health.py`
- `README.md`
- This task file

## Acceptance criteria
- [ ] Checks are loopback-only, bounded, and non-secret.
- [ ] One unavailable interface does not produce invented readiness.
- [ ] Tests pass.

## Owner decisions
None.

## Completion report
Pending.
