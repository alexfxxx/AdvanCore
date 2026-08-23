# ADR-022: Governed Worker Fallback Boundary

Status: Accepted for TASK-022 implementation review

## Context

The governed development loop could stop when Kimi or Kimi-Swarm was locally
unavailable, even though another approved local implementation worker existed.
Embedding vendor-specific control or silently changing workers would weaken the
authority boundary and make execution ambiguous.

## Decision

AdvanCore owns a fixed adapter registry and permits an explicitly configured,
single fallback hop. Fallback is eligible only for a bounded provider
availability classification and only after proving that branch, HEAD, index,
worktree, and remotes are unchanged. All other failures stop fail-closed.

Codex is supported as a local implementation-worker adapter using code-owned
argv, an ephemeral session, workspace-write sandboxing, and denied interactive
approvals. No arbitrary command, credential, cloud/remote mode, web search,
additional writable root, or sandbox bypass is exposed.

`agent_runner` remains the authority boundary, implementation workers remain
non-approving actors, and controller review plus TASK-020 remain the only route
to publication.

## Consequences

- Kimi availability no longer creates a mandatory owner courier step when an
  approved fallback was selected in advance.
- Mutation or ambiguous failure by the primary cannot cascade into a second
  worker attempt.
- Adding another worker requires a code change, review, and tests; task input
  cannot introduce one dynamically.
- AdvanCore stays provider-neutral and does not depend on Codex desktop.
