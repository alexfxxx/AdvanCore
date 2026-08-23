# ADR-006 — Controller Review Bundle

## Status

Approved and implemented as part of TASK-010.

## Context

TASK-005 through TASK-009 established a fail-closed local agent runner, real
Kimi execution, post-worker Git verification, explicit approval gating, local
audit records, and an authority-aware task lifecycle control plane. The runner
already produces durable JSON Lines audit records, but review evidence for a
controller or reviewer was still scattered across terminal output, task files,
Git status, test output, and audit records.

This created a handoff problem: an independent reviewer had to reconstruct the
runner's conclusion from multiple sources, and there was no single,
machine-readable artifact summarizing what the worker did, what changed, and
what the runner recommends the controller do next.

## Decision

Introduce a deterministic, machine-readable controller review bundle produced
after every `execute()` invocation that reaches post-worker verification.

Key choices:

1. **Local JSON artifact.** Bundles are written as formatted JSON files under
   `.agent_runner/review/`. The directory is already gitignored via the existing
   `.agent_runner/` rule, so bundles never leak into version control by default.

2. **Bounded, safe metadata only.** Each bundle contains:
   - timestamp,
   - task ID and filename,
   - task lifecycle status when available,
   - branch, pre-worker HEAD, post-worker HEAD,
   - runner final status,
   - worker type and worker success,
   - post-worker verification result and messages,
   - exact changed paths,
   - concise diff summary/statistics,
   - audit-record reference,
   - recommended controller action.

3. **Recommended action derived from runner evidence only.** The bundle may
   recommend only one of:
   - `REVIEW` — worker succeeded and post-worker verification passed.
   - `REWORK` — worker failed but repository verification remained safe.
   - `BLOCKED` — repository safety verification failed or review evidence could
     not be produced reliably.

   The bundle must never recommend or assert `APPROVED`.

4. **Exclusions.** Bundles must not contain credentials, environment dumps,
   connection strings, full task bodies, full worker transcripts,
   customer/business data, or arbitrary command output.

5. **Read-only inspection CLI.** A new `review-bundle show` subcommand displays
   a concise summary of a bundle. `show` with no argument resolves to the latest
   bundle. The command never mutates repository state.

6. **Explicit failure reporting.** Bundle-write failures are surfaced in runner
   output and in `RunnerResult`; they do not silently disappear. A bundle that
   cannot be written recommends `BLOCKED` because reliable review evidence is
   unavailable.

7. **No authority expansion.** The bundle does not grant commit, push, merge,
   deployment, owner, or approval authority to the runner or worker. It is a
   read-only handoff artifact for a human controller/reviewer.

## Consequences

- Controllers and reviewers now have a single, deterministic artifact to
  evaluate after a worker run.
- The bundle reinforces the existing safety model: worker success alone is
  insufficient; repository verification and runner evidence determine the
  recommended action.
- Review metadata remains local and under the same `.agent_runner/` gitignore
  rule as audit records, avoiding accidental commits.
- The deterministic JSON format supports future automation (e.g., signed
  bundles, CI ingestion) without changing the core design.

## Alternatives considered

- **Embed review metadata inside the existing audit JSONL file.** Rejected:
  audit records are append-only traces of every invocation; review bundles are
  standalone handoff artifacts that should be easy to locate, inspect, and
  transmit as single files.
- **Include the full worker transcript or stdout/stderr.** Rejected: the task
  explicitly forbids full transcripts, and bounded review metadata is
  sufficient for controller handoff.
- **Allow the bundle to recommend `APPROVED` when tests pass.** Rejected:
  passing tests do not equal review acceptance; only a controller/reviewer or
  owner may approve.
- **Write bundles to a project-visible directory outside `.agent_runner/`.**
  Rejected: keeping bundles under `.agent_runner/review/` ensures they are
  gitignored and scoped to the local runner.

## Compliance / risks

- No production data, secrets, or production databases are accessed.
- No schema changes or migrations were introduced.
- No Git commit/push/merge/branch-switch behavior was added.
- The bundle excludes credentials, environment dumps, full task bodies, worker
  transcripts, and customer/business data.
- The bundle cannot be used by a worker to self-approve; it recommends only
  `REVIEW`, `REWORK`, or `BLOCKED`.
