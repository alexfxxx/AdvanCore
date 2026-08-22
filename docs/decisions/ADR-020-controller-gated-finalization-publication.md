# ADR-020 — Controller-Gated Finalization and Branch Publication

**Date:** 2026-08-21
**Status:** Accepted
**Branch:** `agent-control-foundation`
**Task:** TASK-020

---

## Context

The AdvanCore auto-pipeline (TASK-017/TASK-018) automates implementation and
verification, producing a `READY_FOR_APPROVAL` review bundle. A controller or
owner must still separately approve `REVIEW → APPROVED`. After approval, the
remaining publication choreography—worker lifecycle transitions, exact-path
staging, commit, clean-tree verification, push, and post-push synchronization—is
repetitive and error-prone when performed manually.

TASK-020 automates that choreography without changing the authority model.
Publication must remain impossible without a separately valid controller
`APPROVE` decision and matching verified evidence.

## Decision

Add `advancore/agent_runner/finalize.py` as the controller-gated finalization
layer, with the following design choices:

1. **Authority is consumed, not created.** The finalizer loads an existing
   controller decision record and rejects anything other than a valid
   controller `APPROVE`. It never infers approval from tests, worker output,
   bundle state, or transport success.
2. **Reuse existing governance artifacts.** The finalizer consumes the TASK-010
   review bundle, TASK-011 controller decision record, TASK-012
   decision-lifecycle bridge, TASK-009 lifecycle transition helpers, and
   existing Git info/audit helpers rather than duplicating authority checks.
3. **Worker transitions are orchestrated, not authorized.** If the task is still
   `READY` or `IN_PROGRESS`, the finalizer applies `READY → IN_PROGRESS → REVIEW`
   using the existing worker-attributed transition path. It does not skip states
   and does not apply transitions when evidence is stale.
4. **Controller approval uses the existing bridge.** `REVIEW → APPROVED` is
   applied through `apply_controller_decision()` so actor attribution and audit
   remain unchanged.
5. **Exact-path staging.** Only the verified `changed_paths` plus the
   legitimately modified task file are added to the index. `git add .`, `-A`,
   and wildcards are never used.
6. **Independent staged-scope reverify.** After staging, the index is inspected
   and compared to the approved set; any mismatch stops before commit.
7. **Bounded commit message.** The default message is `agent: <normalized task
   title>`. An optional controller-supplied message is accepted only if it is
   non-empty and contains no newlines or carriage returns.
8. **Post-commit verification.** The finalizer verifies a clean working tree,
   expected commit parent, non-merge commit, and exact commit contents before
   any push.
9. **Push only the current verified feature branch.** Push is limited to
   `git push origin <current-branch>` targeting `origin/<same-branch>`. Force
   push, history rewrite, tag creation, ref deletion, and merge commits are
   impossible through this command. `main` cannot be pushed.
10. **Post-push synchronization verification.** After push, local HEAD is
    compared to `origin/<same-branch>` and the working tree is confirmed clean.
11. **Preview by default.** Without `--apply`, the finalizer performs all safe
    validation and reports intended actions without mutating lifecycle state,
    index, HEAD, or remote state.
12. **Bounded audit artifacts.** Every attempt writes a `mode: "finalize"` audit
    record to `.agent_runner/audit/runner.jsonl`. Successful attempts also
    append to `.agent_runner/finalize/finalize.jsonl`. Both contain only safe
    metadata and exclude transcripts, secrets, and environment dumps.

## Consequences

- Owners/controllers retain exclusive approval authority; the runner only
  executes a separately recorded decision.
- Repetitive post-approval Git choreography is eliminated for verified feature
  branches.
- Staging, commit, and push remain fail-closed: stale evidence, scope mismatch,
  dirty trees, upstream mismatch, or push failure stop the process and report
  bounded evidence.
- The implementation stays within the allowed TASK-020 file scope and reuses
  existing controller/lifecycle/audit/Git helpers.

## Rejected alternatives

- **Infer approval from `READY_FOR_APPROVAL` or passing tests.** Rejected:
  verification is evidence, not authority; only a controller decision can
  approve.
- **Broaden staging with `git add -A` or wildcard paths.** Rejected: exact-path
  staging is required to prevent accidental commits.
- **Allow force push or history rewrite.** Rejected: publication must be
  fast-forward and non-destructive.
- **Push `main` or any branch other than the current verified feature branch.**
  Rejected: `main` remains untouched and publication must target the verified
  branch only.
- **Merge to `main` as part of finalization.** Rejected: merging is explicitly
  out of scope and remains a separate owner/controller decision.

## Compliance notes

- No production database access, credential storage, or deployment action is
  introduced.
- GitHub remains the source-of-truth; the finalizer only pushes the current
  feature branch to its configured `origin/<same-branch>` upstream.
- Secrets, credentials, and customer data are excluded from finalization
  artifacts.
