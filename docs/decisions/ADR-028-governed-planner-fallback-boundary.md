# ADR-028 — Governed Planner Fallback Boundary

STATUS: ACCEPTED

## Context

Owner-goal intake depended on Kimi planners and proposal calls did not share the
bounded process lifetime used by implementation workers. Planner fallback must
not grant implementation, lifecycle, Git, or task-file authority.

## Decision

Use a fixed proposal-planner registry: `dry-run`, `kimi`, `kimi-swarm`, and
`codex`. Codex runs locally with fixed argv, ephemeral state, read-only sandbox,
denied approvals, a verified repository root, one bounded prompt, and governed
timeout/process-group termination. All executable planners use the shared
bounded runner.

Fallback is explicit, absent by default, and limited to one hop. It is eligible
only for executable unavailability, quota/capacity exhaustion, or unavailable
authentication, and only when independent Git evidence proves branch, HEAD,
index/worktree, and remotes unchanged. Every other failure stops closed.

The planner output remains untrusted data. `agent_runner.goal_task` alone parses,
validates, assigns the task identity/path/schema, renders `STATUS: DRAFT`, and
writes the task. Audit artifacts and checkpoints store bounded policy and
recovery metadata but never transcripts or credentials. Resume retains the
checkpoint policy and rejects a conflicting explicit override.

## Consequences

Goal intake can continue across one clean provider-availability failure without
silently changing provider or expanding authority. Timeouts, malformed output,
ambiguous failures, and mutations require controller/owner intervention.

## Database impact

None.
