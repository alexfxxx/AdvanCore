# TASK-115 — Import Review Queue and Duplicate Detection

STATUS: COMPLETE

## Objective

Turn a validated operational CSV preview into a read-only review queue that
clearly identifies invalid rows, duplicates within the uploaded file, exact
matches already in the database, and rows eligible for later publication.

## Business context

Operators need to understand what an upload would do before any master record
can be created. Duplicate rules must follow existing unique identifiers and
must not invent fuzzy matching or customer-specific policy.

## In scope

- Deterministic review classifications for every preview row.
- Exact duplicate checks using registration number, route code, and optional
  driver/customer reference fields already governed by the database model.
- Read-only comparison with current database records.
- A visible review queue and truthful summary in Transport Operations Setup.
- Focused service and presentation tests.

## Out of scope

- Database writes, migrations, record publication, fuzzy/name/address matching,
  real data, external APIs, credentials, billing, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-115-import-review-duplicate-detection.md`
- `advancore/services/operational_import_review_service.py`
- `advancore/pages/operations.py`
- `tests/test_operational_import_review_service.py`
- `tests/test_operations_page.py`

## Database impact

Read-only queries against the selected master register. No schema or data
changes.

## Acceptance criteria

- [ ] Invalid rows remain blocked.
- [ ] Every occurrence of a repeated non-empty identity in one file is flagged.
- [ ] Exact existing identities are flagged without fuzzy inference.
- [ ] Rows with no duplicate evidence are shown as ready for later publication.
- [ ] The review queue performs no write and offers no publication action.
- [ ] Focused and full tests pass; Bugbot, CI, and GitGuardian are clean.

## Owner decisions

None. Exact comparison reuses current database uniqueness rules. Fuzzy or
name-based duplicate policy remains explicitly deferred.

## Completion report

### Implemented

- Added read-only classifications for invalid, repeated-in-file,
  already-existing, and publication-ready rows.
- Added exact comparison against current normalized unique identifiers.
- Added a truthful review queue and summary without a publication action.

### Files changed

- `tasks/TASK-115-import-review-duplicate-detection.md`
- `advancore/services/operational_import_review_service.py`
- `advancore/pages/operations.py`
- `tests/test_operational_import_review_service.py`
- `tests/test_operations_page.py`

### Database changes

None. Existing operational registers are queried read-only.

### Tests and results

- Focused after independent-review repair: `32 passed in 1.41s`.
- Full repository after independent-review repair: `1207 passed, 2 skipped in
  177.52s`.
- `git diff --check`: passed.

### Assumptions

Rows without optional driver/customer references cannot be proven duplicates
and remain eligible for later operator review.

### Risks / unresolved issues

Publication remains deferred to TASK-116.

### Decisions required

None.

### Recommended next step

Implement TASK-116 governed master-record publication after integration.
