# TASK-171 — Primary Console Projects

STATUS: COMPLETE

## Objective

Move the existing Project create, edit and archive workflows into the port-8000
record manager using `ProjectService` and its existing fields only.

## Approved scope

- List and select Projects in the manager.
- Create with name and optional description.
- Edit active Projects and archive only after explicit review/confirmation.
- Preserve Activity Log recording and existing lifecycle validation.

## Out of scope

New fields, restoration/unarchive, deletion, schema changes, imports and real
operational test writes.

## Acceptance criteria

- [x] Create/edit/archive delegate to `ProjectService` inside one transaction.
- [x] Archived and unsupported states remain read-only.
- [x] The dashboard summary refreshes after successful actions.
- [x] Focused tests and completion evidence pass.

## Completion report

Projects are available in the primary record manager with reviewed create,
active-only edit and archive actions. Existing lifecycle and Activity Log
behavior remain service-owned. Bugbot and all final tests are clean.
