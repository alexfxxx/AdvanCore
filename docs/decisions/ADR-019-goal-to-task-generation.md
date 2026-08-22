# ADR-019 — Goal-to-Task Generation Foundation

**Date:** 2026-08-21  
**Status:** Accepted  
**Branch:** `agent-control-foundation`  
**Task:** TASK-019

---

## Context

The AdvanCore auto-pipeline (TASK-017/TASK-018) automates most of the
implementation loop, but a human/controller still has to turn an owner goal
into a complete governed `TASK-###` specification before the pipeline can
begin.  TASK-019 introduces a governed front door that converts a bounded
owner goal into a deterministic `STATUS: DRAFT` task file.

The critical constraint is that the planner must remain an **untrusted
planning assistant**.  The runner must retain full authority over task ID,
status, filename safety, repository integrity, and the final rendered task
document.

## Decision

Add `advancore/agent_runner/goal_task.py` as the goal-to-task generation layer,
with the following design choices:

1. **Planner is proposal-only.**  Kimi/Kimi-Swarm receives a canonical
   instruction that forbids repository mutation, authority assignment, and
   self-approval, and must return a single JSON proposal between deterministic
   markers.
2. **Runner validates everything.**  The runner parses the proposal, enforces a
   versioned schema, rejects unsafe/oversized/unknown fields and paths, assigns
   the next `TASK-###` ID, slugs the title, renders the canonical markdown, and
   writes the file.
3. **Repository integrity is verified.**  Pre- and post-planner snapshots
   (branch, HEAD, remotes, worktree state) are compared; any planner-side
   mutation blocks task-file creation.
4. **Output is always `STATUS: DRAFT`.**  No lifecycle transition or automatic
   execution occurs.
5. **CLI defaults to dry-run.**  `--execute` is required to invoke a planner and
   write a task file.
6. **Bounded artifact only.**  A JSON Lines record under
   `.agent_runner/goal_task/goal_task.jsonl` records safe metadata; it excludes
   full transcripts, secrets, and environment dumps.

## Consequences

- Owners can express goals in natural language and receive a structured DRAFT
  task without leaving the runner boundary.
- The controller/reviewer retains exclusive `DRAFT -> READY` authority.
- The planner cannot broaden its own authority, execute the task, or mutate the
  repository without detection.
- The implementation stays within the existing seven-file TASK-019 scope and
  reuses the `WorkerAdapter` boundary, Git snapshot helpers, and task-file
  conventions.

## Rejected alternatives

- **Let the planner write the task file directly.**  Rejected: the runner must
  own task ID, status, and filename safety.
- **Allow the planner to propose a task ID or `READY` status.**  Rejected:
  task authority must stay with the runner/controller.
- **Automatically run the auto-pipeline on the generated task.**  Rejected:
  TASK-019 stops at DRAFT; execution requires a separate controller/owner
  transition.

## Compliance notes

- No production database access, credential storage, or deployment action is
  introduced.
- Generated DRAFT tasks preserve unresolved owner decisions for explicit
  controller/owner review.
- GitHub remains the source-of-truth; the runner does not commit or push.
