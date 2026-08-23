# ADR-007 — Controller Decision Record

## Status

Approved and implemented as part of TASK-011.

## Context

TASK-005 through TASK-010 established a fail-closed local agent runner, real
Kimi execution, post-worker Git verification, explicit approval gating, local
audit records, an authority-aware task lifecycle control plane, and a controller
review bundle.

The review bundle carries trusted runner evidence from the worker to an
independent controller/reviewer, but the return path from that review back into
the local control plane was still manual: a controller would communicate a
decision through terminal or chat instructions. There was no standardized,
machine-readable artifact recording the controller's decision against a specific
review bundle.

## Decision

Introduce a deterministic, machine-readable controller decision record stored
locally under `.agent_runner/decisions/`.

Key choices:

1. **Local JSON artifact.** Decision records are written as formatted JSON files
   under `.agent_runner/decisions/`. The directory is already gitignored via the
   existing `.agent_runner/` rule, so decision records never leak into version
   control by default.

2. **Bounded, safe metadata only.** Each record contains:
   - timestamp,
   - task ID and filename,
   - review-bundle path/reference,
   - review-bundle task identity,
   - review-bundle branch,
   - review-bundle pre/post HEAD when available,
   - controller decision,
   - bounded rationale/note,
   - actor role,
   - decision-record version.

3. **Allowed decisions are exactly three.**
   - `APPROVE` — independent controller accepts the implementation for the next
     human-gated publication step.
   - `REWORK` — implementation requires further worker changes.
   - `BLOCKED` — review cannot proceed safely or required evidence/decision is
     missing.

4. **No automatic action.** An `APPROVE` decision record does not stage, commit,
   push, merge, deploy, or automatically transition the task lifecycle. It is a
   local record only.

5. **Worker cannot record a controller decision.** The actor role `worker` is
   explicitly rejected. Only `controller` and `owner` roles may record a
   controller decision.

6. **Validation fails closed.** The decision builder validates:
   - the decision value is known,
   - the actor role is not `worker`,
   - the linked review bundle is present and parseable,
   - explicit task identity in the request matches the bundle,
   - required bundle linkage fields (task ID, filename, branch, pre HEAD) are
     present.

7. **Exclusions.** Decision records must not contain credentials, environment
   dumps, connection strings, full task bodies, full worker transcripts,
   customer/business data, or arbitrary command output.

8. **CLI support.** A new `controller-decision` subcommand provides:
   - `record <bundle-or-latest> --decision <value> --actor <role> --note "..."`
   - `show <path-or-latest>` (read-only)

9. **Audit integration.** Every decision-record creation appends a safe
   metadata record to the existing `.agent_runner/audit/runner.jsonl` file.

## Consequences

- Controllers and reviewers can now record an explicit, auditable decision
  against a specific review bundle.
- The return path from independent review back into the local control plane is
  standardized without automating commit/push/merge/deployment.
- Decision artifacts remain local and gitignored, avoiding accidental commits.
- The deterministic JSON format supports future automation (e.g., CI ingestion,
  signed records) without changing the core design.

## Alternatives considered

- **Automatically transition the task status on `APPROVE`.** Rejected: the task
  explicitly forbids automatic lifecycle transitions; task status changes remain
  separately gated through the existing `transition` command.
- **Allow the worker to record a decision.** Rejected: workers must never act as
  controller/reviewer actors or approve their own work.
- **Include the full review bundle content inside the decision record.**
  Rejected: the decision record links to the bundle by reference and copies only
  bounded identity/evidence fields, keeping it small and auditable.
- **Write decision records to a project-visible directory outside
  `.agent_runner/`.** Rejected: keeping records under `.agent_runner/decisions/`
  ensures they are gitignored and scoped to the local runner.

## Compliance / risks

- No production data, secrets, or production databases are accessed.
- No schema changes or migrations were introduced.
- No Git commit/push/merge/branch-switch behavior was added.
- Decision records exclude credentials, environment dumps, full task bodies,
  worker transcripts, and customer/business data.
- A worker cannot use an `APPROVE` decision record to self-approve; worker
  actors are explicitly rejected.
