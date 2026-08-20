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

## Rules
1. Read `AGENTS.md` before any task.
2. Work only on tasks marked READY or REWORK.
3. Do not silently expand scope.
4. Record assumptions instead of inventing missing business rules.
5. Do not merge to `main` autonomously.
6. Every task must have acceptance criteria and completion reporting.
7. One task should represent the smallest practical independently reviewable unit of work.

## Naming
Use `TASK-###-short-name.md`.

## Recommended flow
DRAFT -> READY -> IN_PROGRESS -> REVIEW -> APPROVED

If review fails:
REVIEW -> REWORK -> IN_PROGRESS -> REVIEW
