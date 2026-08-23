# AdvanCore Task Queue

This directory is the controlled work queue for AI-assisted development.

## Status values
- DRAFT: requirement is incomplete; agents must not implement.
- READY: approved for implementation.
- IN_PROGRESS: actively being worked.
- REVIEW: implementation completed and awaiting review.
- REWORK: changes requested after review.
- APPROVED: accepted for merge/release according to the normal GitHub workflow.
- BLOCKED: cannot proceed without a decision or dependency.

## Authoritative lifecycle state machine

```
DRAFT ──► READY ──► IN_PROGRESS ──► REVIEW ──► APPROVED
                      ▲               │
                      └───────────────┘
                          REWORK
```

Allowed normal transitions:
- DRAFT → READY
- READY → IN_PROGRESS
- IN_PROGRESS → REVIEW
- REVIEW → APPROVED
- REVIEW → REWORK
- REWORK → IN_PROGRESS

BLOCKED handling:
- Any non-final working state (DRAFT, READY, IN_PROGRESS, REVIEW, REWORK) may move to BLOCKED when a dependency or decision prevents progress.
- BLOCKED may be released to READY or REWORK only by an authorized controller/reviewer.
- APPROVED is final and cannot be returned to BLOCKED.

## Actor responsibilities

| Role | Authority |
|------|-----------|
| worker | READY → IN_PROGRESS, REWORK → IN_PROGRESS, IN_PROGRESS → REVIEW. A worker must not approve its own work. |
| controller / reviewer | DRAFT → READY, REVIEW → APPROVED, REVIEW → REWORK, and all BLOCKED transitions. |
| owner | Includes controller/reviewer authority. Owner approval remains required for any higher-impact decision already gated elsewhere. |

## Applying lifecycle changes

The local agent runner provides an authority-aware `transition` command. By
default it is dry-run / preview only. The task file is mutated only when
`--apply` is passed explicitly.

Preview:
```bash
.venv/bin/python -m advancore.agent_runner transition TASK-009 --to IN_PROGRESS --actor worker
```

Apply:
```bash
.venv/bin/python -m advancore.agent_runner transition TASK-009 --to IN_PROGRESS --actor worker --apply
```

The command only rewrites the single `STATUS:` line; the rest of the task body is
preserved.

## Rules
1. Read `AGENTS.md` before any task.
2. Work only on tasks marked READY or REWORK.
3. Do not silently expand scope.
4. Record assumptions instead of inventing missing business rules.
5. Do not merge to `main` autonomously.
6. Every task must have acceptance criteria and completion reporting.
7. One task should represent the smallest practical independently reviewable unit of work.
8. Lifecycle changes must be validated by the runner and recorded in the local audit trail.

## Naming
Use `TASK-###-short-name.md`.

## Recommended flow
DRAFT -> READY -> IN_PROGRESS -> REVIEW -> APPROVED

If review fails:
REVIEW -> REWORK -> IN_PROGRESS -> REVIEW
