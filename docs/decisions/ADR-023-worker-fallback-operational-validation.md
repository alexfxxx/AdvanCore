# ADR-023: Worker Fallback Operational Validation

Status: Accepted for TASK-023 implementation review

## Context

TASK-022 defined a fail-closed, single-hop worker fallback boundary. Its unit
tests established policy semantics, but the milestone also required evidence
that real adapter argv, subprocess execution, Git mutation detection, reporting,
and persistence behave together without relying on live provider availability.

## Decision

Validate fallback with deterministic integration tests that create temporary
Git repositories and fake worker executables on an isolated `PATH`. Exercise
the production Kimi-Swarm and Codex adapters and the existing auto-pipeline,
while replacing only live worker/provider behavior and expensive verification
commands with controlled fixtures.

Operationally, require explicit fallback selection. Permit the one fallback
only for a recognised availability classification with unchanged branch, HEAD,
index, worktree, and remotes. Treat an unknown failure, any ambiguous mutation,
or fallback failure as terminal. Persist only bounded worker identities,
classification, integrity result, and terminal outcome.

Keep responsibility divided as follows: `agent_runner` owns permanent policy,
integrity, evidence, and verification behavior; local clients and operators own
launching, monitoring, checkpointed resume, and exception presentation. Neither
worker choice nor successful verification creates controller or TASK-020
publication authority.

## Validation result

The TASK-023 integration suite proves eligible Kimi-Swarm-to-Codex fallback,
all five Git-state mutation stops plus unknown-failure stop, one-hop
terminality, CLI fail-closed policy, downstream verification, and bounded
report/artifact content. It makes no network or live-provider calls.

## Consequences

- Provider unavailability can be handled locally without making fallback
  implicit or weakening Git-integrity gates.
- Tests cover the subprocess boundary deterministically and remain independent
  of installed provider CLIs.
- Operators have one documented review/resume procedure.
- A third worker hop, transcript persistence, controller self-approval, and
  automatic publication remain prohibited.
