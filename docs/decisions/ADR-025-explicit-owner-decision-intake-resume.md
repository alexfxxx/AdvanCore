# ADR-025 — Explicit Owner Decision Intake and Resume

STATUS: ACCEPTED

Date: 2026-08-23

## Context

The governed orchestration loop already pauses for task approval and
implementation review, but an operator previously had to relay an owner choice
through separate lifecycle or controller-decision commands before resuming.
That courier sequence increased friction without adding authority validation.

## Decision

Add a fixed `OwnerAction` enum to orchestration resume. Owner actions require a
checkpoint run ID, are valid only at their exact gate, and cannot be combined
with resume-time adapter, budget, or timeout changes. Preview remains the
default and validates all intended calls without writing state.

Task actions call the existing lifecycle API with actor `owner` against the
checkpointed DRAFT task. Implementation actions build the existing TASK-011
`ControllerDecision` with actor `owner`, exact task/bundle and branch/HEAD
evidence, and an optional single-line 400-character note. Existing handoff
reconciliation and orchestration phase handlers continue the run; lifecycle,
rework, finalization, staging, commit, and push logic are not duplicated.

The checkpoint/report records only action, actor, evidence path,
preview/applied state, and one next action. Natural-language parsing and
transcript persistence are excluded. Exact already-recorded evidence can be
reconciled after interruption; conflicts, ambiguity, stale evidence, consumed
actions, and phase mismatch fail closed.

## Consequences

- One explicit owner command can record authority and resume the same run.
- Preview is safe for inspection and produces no durable state.
- Local clients remain couriers, not decision-makers; workers and adapters gain
  no owner authority.
- Authentication, remote intake, webhooks, daemons, and GUIs remain out of
  scope.
- Operators must retain and use the exact run ID and fixed action value.
