# ADR-030 — Knowledge Replacement History

STATUS: ACCEPTED

## Context

Approved Knowledge is deliberately immutable. Corrections therefore require a
new draft without erasing which content the owner previously approved or when
it was replaced.

## Decision

Represent corrections as a forward-only self-referencing chain. A replacement
draft points to the exact approved source through
`replaces_knowledge_item_id`. It copies the source's saved business fields for
editing but never changes the source record.

Only one non-archived direct replacement may exist for a source. Archiving a
replacement draft permits a fresh attempt. Until replacement approval, the
source remains `approved` and official. Approval of the replacement and the
source transition to `superseded` occur in one caller-owned transaction.
Superseded records preserve their original approval evidence and remain
read-only.

Database checks reject self-reference and superseded rows without approval
metadata. A partial unique index enforces one active direct replacement under
concurrent writes. Activity Log records only bounded lifecycle actions and
numeric Knowledge identifiers, never content or titles.

## Consequences

The owner can correct official Knowledge without silent rewriting, and every
version remains auditable. The first scope supports a linear history rather
than branching or rollback. Authentication and biometric identity remain
separate security decisions.

## Database impact

- Add one nullable self-referencing foreign key.
- Add no-self-reference and superseded-metadata checks.
- Add one partial unique index for active direct replacements.
- Preserve all existing rows unchanged.

## Owner approval

The owner authorised TASK-076 on 25 August 2026, continuing the approved
TASK-074 replacement-draft correction rule.
