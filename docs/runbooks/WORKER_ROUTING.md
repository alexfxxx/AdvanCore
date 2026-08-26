# Kimi-first worker routing

Unattended implementation uses the fixed registered route Kimi-Swarm first,
Gemini second, and Codex last. Kimi still passes the TASK-044 fresh usage,
weekly percentage, runtime and isolation checks. The auto-pipeline moves to the
next worker only for an eligible provider failure after repository integrity is
proven unchanged.

Standing authority is consumed at actual launch. Fallback consumes a separate
approved-fallback action. Neither route receives new credentials or approval,
merge, `main`, deployment, business or compliance authority.

## Activated Gemini implementation worker

Gemini uses the fixed local `agy` Antigravity CLI after owner-present Google
authentication and a synthetic smoke evaluation. It is approved only for
implementation and fallback roles, not planning or review. The adapter owns its
executable name and arguments, uses print mode, accept-edits mode, workspace
sandboxing, disabled slash expansion, JSON output, and a bounded timeout. It
never enables the permission-bypass flag or accepts caller-selected models,
agents, plugins, endpoints, API keys, or arbitrary command options.

The worker process receives a minimal environment. `HOME` lets the CLI use its
own existing OAuth session, but controller API keys, database URLs, GitHub
credentials, proxy variables, and loader settings are not inherited. Input
credential screening and post-worker repository verification remain mandatory.
An unavailable Google Pro balance is not treated as proof that Gemini cannot
run; actual executable, authentication, quota, and capacity failures are
classified at launch.

## Governed selection

Selection is separate from launch. For each bounded role, AdvanCore owns a
fixed preference order and accepts only explicit controller availability
evidence. Implementation prefers Kimi-Swarm and then Codex; planning prefers
Kimi and then Codex. Missing or stale evidence is unavailable. Registry
approval and role eligibility are checked before a name can be selected.

Selection does not consume standing authority or start a process. The selected
adapter must still pass the established credential, usage, isolation,
repository-integrity, timeout, and launch checks. An unreadable balance is not
itself a launch failure; executable, authentication, quota, and capacity facts
are classified from the bounded launch result.

## Safe failover checkpoint

Provider-neutral failover state contains only bounded identifiers, the fixed
role, selected/attempted worker names, an eligible provider-failure class, and
a repository fingerprint. It stores no prompt, worker output, environment,
credential, or raw provider error.

Advancement requires the exact selected worker, an eligible classified failure,
an unchanged fingerprint, and a different available approved worker from the
fixed selection policy. The run is limited to a primary plus two fallbacks.
Checkpoint selection and persistence do not launch workers or consume standing
authority; runtime pipeline integrity checks still apply.
