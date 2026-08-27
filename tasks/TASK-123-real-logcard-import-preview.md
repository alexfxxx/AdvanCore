# TASK-123 — Real Fleet Logcard Import Preview

STATUS: APPROVED

## Objective

Produce a redacted, read-only review of the 27 owner-supplied LTA logcards so
the owner can approve the exact Fleet mapping before any operational database
write occurs.

## Facts

- The owner supplied 27 vehicle logcards for three registered business owners.
- TASK-119 provides the approved Fleet fields and keeps unknown values null.
- Source documents remain outside Git and contain identifiers and addresses
  that the Fleet import does not need.
- The live local database contained no vehicles or legal entities when the
  preview was prepared.

## In scope

- Extract only TASK-119-approved identity and vehicle-detail fields.
- Normalize vehicle type to Bus, lorry or car while retaining exact LTA seating.
- Exclude owner identifiers, addresses and unrelated source-document content.
- Show all extracted vehicles in a filterable local review artifact.
- Identify filename/source conflicts and field inconsistencies for owner review.
- Keep the preview read-only and outside the operational database.

## Out of scope

- Database writes, repository copies of source documents or real fleet values,
  estimates, finance, insurance, parking, deployment, credentials and `main`.

## Allowed changed-file scope

- `tasks/TASK-123-real-logcard-import-preview.md`
- A local ignored/scratch review artifact outside the repository.

## Database impact

None. Approval of the preview is a separate gate before TASK-124.

## Acceptance criteria

- [ ] Exactly 27 unique registrations are represented.
- [ ] Every row has registered owner, make/model, manufacture year, exact
      passenger capacity and normalized vehicle type.
- [ ] No owner identifier, address or source PDF is copied into Git.
- [ ] Unknown costs remain unknown and no amount is inferred.
- [ ] The owner explicitly approves or rejects the preview before TASK-124.

## Owner decisions

The owner approved TASK-123 through TASK-125 and explicitly required the
preview to remain a gate before the 27-vehicle database write.

