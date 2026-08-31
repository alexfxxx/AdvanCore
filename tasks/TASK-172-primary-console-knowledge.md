# TASK-172 — Primary Console Knowledge

STATUS: COMPLETE

## Objective

Move the existing Knowledge draft, edit, approval, archive and forward-only
replacement workflows into the port-8000 record manager.

## Approved scope

- Use only `KnowledgeService` and existing title/content/lifecycle fields.
- Keep owner approval explicit and based on the currently saved draft.
- Preserve approved/superseded history and replacement constraints.
- Refresh the primary Knowledge summary after successful actions.

## Out of scope

Direct edits to approved Knowledge, deletion, new fields, schema changes,
imports and real operational test writes.

## Acceptance criteria

- [x] Every lifecycle action delegates to `KnowledgeService`.
- [x] Draft, approved, archived and superseded states render truthfully.
- [x] Approval/archive/replacement require explicit reviewed confirmation.
- [x] Focused tests and completion evidence pass.

## Completion report

Knowledge draft and lifecycle actions are available in the primary manager.
Approval shows the complete content and is transactionally bound to the locked
saved timestamp and SHA-256 content digest, so stale review fails closed.
Bugbot and all final tests are clean.
