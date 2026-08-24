# Worker data boundary

Routine workers receive a minimal process environment and a governed task path.
Before launch, AdvanCore checks the instruction and referenced task for
high-confidence credential material. A possible match stops the worker with a
controlled owner-review message; the value is never copied into logs or output.

Kimi is additionally prevented by the local operating-system sandbox from
reading common account and repository credential locations. Its own provider
login remains external to AdvanCore. Codex runs through its fixed ephemeral,
workspace-write sandbox and the same input preflight.

This boundary intentionally has no unattended credential override. If a future
task genuinely needs a secret or production data, design a narrow, expiring
capability and obtain explicit owner approval first.
