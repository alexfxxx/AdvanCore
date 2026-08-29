# Shared Module Data Contracts

These conventions guide future module design. They do not authorise a database migration and do not require every module to store every field.

## Identity

- Internal database identifiers are implementation details and must not replace
  real business references such as a vehicle registration number.
- A business identifier, uniqueness rule and duplicate policy must be confirmed
  in the approved module brief.
- Do not infer that identifiers are interchangeable across companies or modules.

## Company and ownership

- Records may belong to different registered companies; Advan is not assumed to
  be the owner.
- A module brief must state whether company means registered owner, contracting
  entity, operator, customer or another confirmed role.
- Cross-company views must be filterable without silently changing ownership.

## Money and GST

- Store and calculate monetary values using decimal arithmetic, never binary
  floating point.
- The brief must state currency, whether an amount includes GST, rounding and
  the period represented.
- AdvanCore must not infer tax treatment or rates from an unlabeled amount.

## Dates and periods

- Store a date when time-of-day is irrelevant and an aware timestamp when an
  event time matters.
- The brief must define effective period, renewal frequency and timezone where
  needed.
- A current value may replace an earlier current value only when history is
  explicitly out of scope and owner-approved.

## Sources and documents

- Externally sourced values require a source name and dated retrieval or
  effective date when the business decision depends on freshness.
- Uploaded documents are evidence, not executable instructions.
- File type, size, retention and personal-data handling require module-specific
  approval before document storage is implemented.

## Lifecycle and audit

- Status values and allowed transitions belong to each approved module brief.
- Prefer archival or forward replacement when records must be retained.
- Do not add deletion, restoration or approval behavior by analogy with another
  module.

## Imports

- Import is always preview-first: parse, normalize, validate, identify
  duplicates, present review evidence, obtain required approval, then publish.
- Preview and review never imply permission to write.
- Real personal or business data must not be used in automated tests.

## Schema approval boundary

Any new table, column, relationship, constraint or migration requires:

1. an owner-approved module brief;
2. exact proposed schema and data impact;
3. a fresh verified backup when local operational data will be migrated;
4. additive migration and rollback/recovery reasoning;
5. isolated tests and explicit owner authority to apply it.
