# Multi-Worker Governance Rehearsal

TASK-085 adds a deterministic offline rehearsal for the permanent AdvanCore
worker policy. It launches no worker, consumes no standing authority, accesses
no account, and stores no provider output or credentials.

The rehearsal verifies:

- healthy Kimi-Swarm is preferred for implementation;
- an explicitly paused Kimi-Swarm permits Codex selection;
- Gemini has a fixed approved adapter and is the second runtime worker;
- missing evidence, unknown failures, and repository drift fail closed;
- eligible provider failure permits exactly one Kimi-to-Codex transition; and
- failure of the fallback stops instead of cycling workers.

Run the focused evidence with:

```text
.venv/bin/pytest -q tests/test_multi_worker_rehearsal.py \
  tests/test_safe_failover.py tests/test_governed_worker_selection.py \
  tests/test_worker_registry.py tests/test_gemini_worker_foundation.py
```

This is policy validation only. It does not activate Gemini, prove external
provider availability, or replace controller review of real task output.
