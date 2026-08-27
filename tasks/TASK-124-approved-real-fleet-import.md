# TASK-124 — Approved Real Fleet Import

STATUS: APPROVED

## Objective

Import the owner-approved 27-vehicle preview into the local operational Fleet
database through the existing TASK-119 validation boundary.

## Preconditions

- The owner explicitly approved the TASK-123 preview.
- A fresh local PostgreSQL backup must be created and verified before writing.
- The live schema must be at the single expected Alembic head.
- The import must fail closed on an unexpected existing vehicle, duplicate
  registration, missing required preview field or changed batch size.

## In scope

- Create the three approved legal-owner records.
- Create 27 vehicle identities and update only source-backed TASK-119 fields.
- Use one database transaction and the existing legal-entity and vehicle
  services; roll back the whole batch on failure.
- Preserve exact LTA passenger capacity independently from model wording.
- Keep source documents and the real import payload outside Git.
- Verify counts and required-field completeness after commit.

## Out of scope

- Overwrites, updates to pre-existing vehicles, partial imports, inferred
  values, source-document storage, finance, parking, insurance, deployment,
  credentials, billing and `main`.

## Allowed changed-file scope

- `tasks/TASK-124-approved-real-fleet-import.md`
- The owner-approved local PostgreSQL operational database.
- Ignored local backup/evidence files.

## Database impact

One atomic data-only transaction may add three legal entities, 27 vehicles and
the existing bounded activity events. No migration or schema change is allowed.

## Acceptance criteria

- [ ] A fresh pre-import backup is created and independently verified.
- [ ] Exactly three owner records and 27 unique vehicles are added atomically.
- [ ] All required preview fields match the approved batch.
- [ ] Unknown finance/current-cost fields remain null.
- [ ] No source PDF or real import payload is committed.
- [ ] A failed precondition or row rolls back the full batch.

## Owner decisions

The owner approved the 27-vehicle TASK-123 preview on 27 August 2026. A road-tax
amount without its required 6- or 12-month period must remain unrecorded rather
than inferred.

