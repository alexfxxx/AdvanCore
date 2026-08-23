# ADR-021 — End-to-End Controller Orchestration

## Status

Accepted — implemented as part of TASK-021.

## Context

TASK-019 through TASK-020 provide the governed stages needed to turn an owner
goal into a DRAFT task, authorize execution, run Kimi/Kimi-Swarm, verify and
repair implementation, obtain an independent controller decision, and safely
publish the current non-`main` feature branch.  The stages previously required
an operator to invoke separate commands and relay artifact identifiers between
them.

Codex desktop can run and monitor the local workflow, but embedding desktop or
vendor-specific control in AdvanCore would make governance dependent on one
operator product.  Conversely, duplicating the existing lifecycle, controller,
verification, or publication rules in a new coordinator would create competing
authority models.

## Decision

Add a provider-neutral, resumable coordinator in
`advancore/agent_runner/orchestration.py`.  It persists bounded, versioned,
atomic checkpoints under ignored `.agent_runner/orchestration/` and delegates
governance-sensitive actions to the existing modules:

- goal-task generation remains owned by TASK-019;
- lifecycle transitions remain owned by TASK-009;
- implementation and bounded repair remain owned by TASK-017/TASK-018;
- review, handoff, adapter, transport, and decision validation remain owned by
  TASK-010 through TASK-016;
- finalization and feature-branch publication remain owned by TASK-020.

The coordinator advances only from revalidated source artifacts and current Git
state.  Passing tests or `READY_FOR_APPROVAL` are evidence, never approval.
Missing, malformed, stale, conflicting, or unauthorized state pauses or fails
closed.

### Rework authority

A controller `REWORK` decision does not invent `READY -> REWORK`.  After a
verified implementation run, the coordinator applies the existing worker-owned
transitions `READY/REWORK -> IN_PROGRESS -> REVIEW`, then applies the recorded
controller decision through the existing decision-lifecycle bridge for
`REVIEW -> REWORK`.  Rework cycles are separately bounded from autonomous
repair attempts.

### Permanent and local responsibilities

AdvanCore permanently owns phase sequencing, correlation, checkpointing,
freshness, idempotency, authority validation, bounded retries, audit evidence,
and safe terminal reporting.

Codex desktop or another local operator may invoke, monitor, and resume the CLI
and present exceptions.  It may assist an explicitly authorized independent
controller only through the existing controller-decision boundary.  Codex,
ChatGPT, OpenAI APIs, desktop automation, and vendor credentials are not runtime
dependencies of the coordinator.

## Consequences

- One command can carry a bounded goal across the existing governed stages and
  pause only at real authority or safety exceptions.
- A run can resume without repeating completed planner, worker, decision, or
  publication actions.
- Checkpoints improve coordination but never replace GitHub or validated source
  artifacts as authority.
- Manual/local controller operation remains a first-class pause/resume path.
- `main`, merge, deployment, force push, releases, production access, and
  automatic owner/controller decisions remain outside the workflow.

## Rejected alternatives

- **Embed Codex/ChatGPT or another remote controller API** — rejected because it
  creates vendor dependence and a second credential/control surface.
- **Let the orchestrator infer approval from successful verification** —
  rejected because verification is evidence, not authority.
- **Let Kimi/Kimi-Swarm self-review or self-approve** — rejected because worker
  and controller roles must remain independent.
- **Copy lifecycle, auto-pipeline, controller, or finalization logic into the
  coordinator** — rejected because duplicated governance rules can diverge.
- **Background daemon, webhook, or hosted control plane** — rejected as
  unnecessary for the local, resumable foundation.
- **Unlimited rework or repair** — rejected because retries must remain bounded
  and auditable.
