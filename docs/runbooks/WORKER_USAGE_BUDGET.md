# Worker usage budget

## Owner policy

Kimi and Kimi-Swarm may consume at most:

- 20% of the provider-reported weekly allowance; and
- 3,600 seconds of cumulative local process runtime in the same provider week.

AdvanCore checks both limits before every Kimi launch. Missing, malformed, stale, future-dated, reset-expired, at-limit, or runtime-exhausted evidence pauses Kimi before process launch. An explicitly configured approved fallback such as Codex may be considered only through the existing provider-failure and repository-integrity gates.

## Permanent AdvanCore responsibility

AdvanCore owns the provider-neutral evidence schema, validation, 15-minute freshness requirement, policy decision, runtime accounting, Dashboard presentation, fail-closed behavior, and approved fallback boundary. No worker may approve itself or bypass `agent_runner` because capacity is unavailable.

Authoritative artifacts use one OS-account-wide location shared by every AdvanCore clone and worktree. On macOS this is `~/Library/Application Support/AdvanCore/agent_runner/usage/`; the non-macOS state path is `~/.local/state/advancore/agent_runner/usage/`. The location is resolved from the operating-system account rather than worker-controlled environment variables:

- `kimi-reported.json` contains only schema version, provider, stable period identifier, weekly percentage, checked/reset timestamps, and an approved source label.
- `kimi-runtime.json` contains only schema version, provider, matching period/reset data, cumulative charged runtime seconds, and conservative next-period carryover.
- `kimi.lock` serializes reservation, execution and settlement so a second Kimi launch cannot race the first.
- `kimi-quarantine.json` appears only when evidence changes during execution or runtime settlement becomes ambiguous; its presence pauses Kimi until an approved controller records fresh valid evidence.

Neither artifact may contain credentials, tokens, browser content, provider responses, prompts, transcripts, environment dumps, customer data, or arbitrary command output.

On the approved macOS execution path, `agent_runner` launches Kimi and all of its descendants inside an OS sandbox that denies writes to the complete controller-state root. Path placement and file modes are not treated as sufficient isolation. Before refreshing or reserving usage, `agent_runner` runs a fixed harmless sandbox capability probe. If the profile cannot actually start—for example, because Codex Desktop is already inside a sandbox—Kimi fails closed before reservation or launch; an approved Codex fallback may still be considered through the unchanged fallback gates.

## Local controller responsibility

The installed Kimi CLI does not currently provide a confirmed stable machine-readable quota command. Codex desktop, another approved local controller, or a future reviewed provider adapter supplies a small trusted probe that obtains the authenticated reading without returning credentials to AdvanCore. This local capability supplies evidence only; it does not gain worker, controller, owner, publication, billing, or deployment authority.

The fixed probe path is `~/Library/Application Support/AdvanCore/agent_runner/probes/kimi-usage` on macOS (or the corresponding `~/.local/state/advancore/agent_runner/probes/kimi-usage` path on other supported systems). Every directory below the protected controller root must be a real owner-controlled directory rather than a symlink. The probe must be a single-link, owner-executable regular file owned by the current OS user and must not be group- or world-writable. This prevents an implementation worker from changing the trusted executable through a repository alias. It receives no arguments and runs with a sanitized environment. Its complete standard output must be one JSON object with exactly these fields:

```json
{"schema_version":1,"provider":"kimi","weekly_used_percent":12,"checked_at":"2026-08-28T03:00:00Z","reset_at":"2026-09-04T02:46:00Z"}
```

The reviewed probe owns interaction with the authenticated Kimi client. It must not emit tokens, provider response bodies, browser contents or diagnostics. Standard output and standard error are each capped at 16 KiB while being collected, the process group is time-bounded, and JSON is decoded only after collection succeeds. When evidence is missing, stale or reset-expired, `agent_runner` invokes this probe automatically before Kimi preflight. Missing, unsafe, failed or invalid probe output keeps Kimi paused and allows only the existing approved fallback evaluation.

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

1. When the existing reading is unavailable or stale, `agent_runner` asks the fixed approved controller probe for a fresh reading.
2. The probe returns only the bounded fields above; AdvanCore strictly validates and records them.
3. The Dashboard shows used percentage, policy limit, local runtime, reset/freshness, and allowed or paused state.
4. Immediately before a Kimi launch, the adapter independently reloads and validates the evidence.
5. If allowed, `agent_runner` exclusively locks the machine-wide ledger and reserves a timeout bounded by both remaining weekly runtime and time remaining before reset. A concurrent launch from any checkout fails closed instead of sharing the same allowance. The absolute reset deadline is checked again immediately before process creation so pre-launch verification cannot consume the guard interval and accidentally start Kimi after reset.
6. Kimi and its descendants run inside the approved OS write-denial boundary around controller state.
7. After completion, the reservation is reconciled down to actual elapsed process time. If the controller exits unexpectedly, the full reservation remains charged and carries into the next verified period rather than disappearing at reset.
8. A guarded deadline prevents a normal run from crossing reset. If suspension or scheduling delay nevertheless causes settlement after reset, the full run charge carries into the next verified provider period instead of being erased.
9. Reset-time adjustments inside the same provider period preserve runtime and cannot lower provider-reported usage. Runtime resets only after the prior reset has passed and a materially later weekly reset is verified.
10. Evidence fingerprints are checked after execution. Any unexpected alteration quarantines the evidence and blocks later launches.
11. If paused, Kimi is not launched. A separately approved fallback may run only if existing integrity checks pass.

## Current transition

The owner introduced the 20% policy after the current Kimi weekly reading had reached 44%. Kimi therefore remains paused until the provider resets and a fresh reading for the new week is recorded. Historical usage is not rewritten or treated as if it were below the new policy.
