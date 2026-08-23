# Worker usage budget

## Owner policy

Kimi and Kimi-Swarm may consume at most:

- 20% of the provider-reported weekly allowance; and
- 3,600 seconds of cumulative local process runtime in the same provider week.

AdvanCore checks both limits before every Kimi launch. Missing, malformed, stale, future-dated, reset-expired, at-limit, or runtime-exhausted evidence pauses Kimi before process launch. An explicitly configured approved fallback such as Codex may be considered only through the existing provider-failure and repository-integrity gates.

## Permanent AdvanCore responsibility

AdvanCore owns the provider-neutral evidence schema, validation, 15-minute freshness requirement, policy decision, runtime accounting, Dashboard presentation, fail-closed behavior, and approved fallback boundary. No worker may approve itself or bypass `agent_runner` because capacity is unavailable.

Authoritative artifacts are stored in a controller-owned directory outside the worker repository: `.advancore-controller/<repository-id>/usage/` beside the repository. This directory is not part of the worker's writable project scope or Git worktree:

- `kimi-reported.json` contains only schema version, provider, stable period identifier, weekly percentage, checked/reset timestamps, and an approved source label.
- `kimi-runtime.json` contains only schema version, provider, matching period/reset data, and cumulative charged runtime seconds.
- `kimi.lock` serializes reservation, execution and settlement so a second Kimi launch cannot race the first.
- `kimi-quarantine.json` appears only when evidence changes during execution or runtime settlement becomes ambiguous; its presence pauses Kimi until an approved controller records fresh valid evidence.

Neither artifact may contain credentials, tokens, browser content, provider responses, prompts, transcripts, environment dumps, customer data, or arbitrary command output.

## Local controller responsibility

The installed Kimi CLI does not currently provide a confirmed stable machine-readable quota endpoint. Codex desktop, another approved local controller, or a future reviewed provider adapter must therefore refresh the bounded snapshot from an authenticated provider reading. This local action supplies evidence only; it does not gain worker, controller, owner, publication, billing, or deployment authority.

Record a fresh reading from the repository root:

```text
.venv/bin/python -m advancore.services.worker_usage_service \
  --repo-root . record \
  --provider kimi \
  --weekly-used 12 \
  --checked-at 2026-08-28T03:00:00Z \
  --reset-at 2026-09-04T02:46:00Z \
  --source kimi-cli
```

Show the current bounded status:

```text
.venv/bin/python -m advancore.services.worker_usage_service --repo-root . show --provider kimi
```

The recording command rejects stale or inconsistent evidence. It never logs into Kimi, reads credentials, or changes a membership plan.

## Operating sequence

1. An approved local controller obtains the current provider reading.
2. It records only the bounded fields above.
3. The Dashboard shows used percentage, policy limit, local runtime, reset/freshness, and allowed or paused state.
4. Immediately before a Kimi launch, the adapter independently reloads and validates the evidence.
5. If allowed, `agent_runner` exclusively locks the ledger and reserves the bounded launch timeout before starting Kimi. A concurrent launch fails closed instead of sharing the same allowance.
6. After completion, the reservation is reconciled down to actual elapsed process time. If the controller exits unexpectedly, the full reservation remains charged.
7. Reset-time adjustments inside the same provider period preserve runtime and cannot lower provider-reported usage. Runtime resets only after the prior reset has passed and a materially later weekly reset is verified.
8. Evidence fingerprints are checked after execution. Any worker-time alteration quarantines the evidence and blocks later launches.
9. If paused, Kimi is not launched. A separately approved fallback may run only if existing integrity checks pass.

## Current transition

The owner introduced the 20% policy after the current Kimi weekly reading had reached 44%. Kimi therefore remains paused until the provider resets and a fresh reading for the new week is recorded. Historical usage is not rewritten or treated as if it were below the new policy.
