# ADR-004 — Runner Post-Worker Verification and Local Audit Records

## Status

Approved and implemented as part of TASK-007.

## Context

TASK-005 and TASK-006 established a fail-closed local agent runner with a
replaceable worker adapter. The proven flow is:

```
GitHub READY task -> Local Agent Runner -> Kimi -> implementation/tests -> human/reviewer gate
```

TASK-006 exposed three gaps:

1. Post-worker Git state was not captured as a first-class verification result.
2. The final `AWAITING_APPROVAL` status was not obvious enough in terminal output.
3. Runner invocations had no durable audit record outside terminal history.

This decision hardens the runner without granting it new authority to commit,
push, merge, deploy, mutate task status, or broaden business scope.

## Decision

Add independent post-worker repository verification and durable local audit
records to the Local Agent Runner.

Key choices:

1. **Capture pre- and post-worker Git snapshots.** `execute()` records the
   repository root, current branch, HEAD SHA, and working-tree state before the
   worker launches and again immediately after the worker exits.

2. **Fail-closed post-worker verification.** The runner blocks approval if:
   - the branch changed,
   - the HEAD SHA changed,
   - the post-worker branch is `main`.
   Changed paths are surfaced clearly. Worker success is kept separate from
   repository-safety verification and cannot override a failed check.

3. **Explicit terminal output.** Successful `execute()` output ends with:
   - `Result status: awaiting_approval`,
   - `Post-worker verification: PASS`,
   - a changed-path summary,
   - a reminder that commit/push remain gated.

4. **Durable JSON Lines audit.** Every `plan()` and `execute()` invocation
   appends one JSON object to `.agent_runner/audit/runner.jsonl`. The record
   contains only safe metadata: timestamp, task ID/filename, mode, worker type,
   branch, pre/post HEAD, pre-flight validation result, worker result,
   post-worker verification result, final status, and changed paths.

5. **No sensitive data in audit records.** Environment dumps, credentials,
   connection strings, full task bodies, full worker transcripts, and business or
   customer data are excluded by design.

6. **Explicit audit-write failure reporting.** If the audit record cannot be
   written, the runner adds a clear warning message and records the failure in
   the result; it does not silently ignore the error.

7. **Audit directory is gitignored.** `.agent_runner/` is added to
   `.gitignore` so local audit records are not committed.

## Consequences

- The runner can detect and block unexpected repository mutations caused by a
  worker, independent of the worker's exit code.
- Every invocation leaves a durable, machine-readable trace for debugging and
  compliance review.
- Approval remains a human/reviewer gate; the runner does not self-approve based
  on passing tests or successful worker completion.
- The audit format is simple JSON Lines, keeping the implementation
  dependency-free and easy to inspect with standard tools.

## Alternatives considered

- **Rely on worker-reported git status.** Rejected: the worker could omit or
  misreport changes. Verification must come from the runner's own Git
  inspection.
- **Use a structured database or remote audit store.** Rejected: introduces
  infrastructure and credentials before the need is proven. Local JSON Lines is
  sufficient for the current scope.
- **Embed the full task body or worker transcript in the audit record.**
  Rejected: would store unreviewed business content and potentially sensitive
  data locally.
- **Make audit-write failure fatal.** Rejected: an operational write failure
  should not mask the primary runner status, but it must be reported explicitly.

## Compliance / risks

- No production data, secrets, or production databases are accessed.
- No schema changes or migrations were introduced.
- The runner continues to use only safe, read-only Git commands for inspection.
- Commit, push, merge, deployment, and task-status mutation remain gated.
