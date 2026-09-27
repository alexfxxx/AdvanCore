# Fuel / AdBlue import release

## Scope

Local HTML-based supplier XLS import with preview and explicit confirmation;
effective-date pricing, duplicate transaction detection, separate product costs,
monthly vehicle consumption and exception checks at `/diesel-import`.
Unknown vehicle identifiers block import. Costs exclude GST; payment is not inferred.
No supplier credentials, prices, excluded fleet identifiers, reports or existing
financial records are shipped in this code release.

The UI is a deterministic import/review workflow, not a general-purpose AI agent.
Screenshots, arbitrary binary Excel layouts and autonomous supplier downloads are
not supported. Historical rate corrections are previewed but blocked pending
separate reconciliation. The supplier credential feature does not schedule work.

## Dependencies and rollout

Preserves the existing local migration chain from `fae192assign` through
`ffi217product`. Earlier schema-only dependencies cover vehicle documents, operating
metrics, driver links, subcontractor bundles, nullable stop times and instalment
fields. Models are included for schema compatibility; their full operating UIs
are outside this release. No applied revision identifiers are rewritten.

Before deployment, back up the operational database separately in private storage
and test the complete upgrade on a disposable PostgreSQL database. This PR does
not deploy or change the running operational database. Do not run downgrade on
production: legacy `fef213nostoptime` downgrade deletes stops lacking a time.

Configure owner-approved `diesel_settings.policy` locally before imports. Its
`excluded_vehicles` list must be explicitly reviewed, including an explicit empty
list if appropriate. Configure effective-date rates locally. No production
configuration or source transactions should be added to GitHub. Reconcile existing
records and register their source transaction identifiers before uploading an
overlapping report; this code cannot identify legacy entries without provenance.

## Checks and limitations

- Matching supplier IDs skip duplicates; changed details require review.
- Financial entries and refuelling facts represent the same costs, not additive costs.
- Monthly views show purchased litres, not measured engine consumption.
- Missing-bus alerts use current active fleet, excluding cars/lorry; historical
  fleet dates and alternate suppliers may explain missing records.
- Spike/drop checks use equal elapsed days, at least three baseline refuellings,
  and a 50% screening threshold. They are review hints, not proof of misuse.
- Partial report coverage is not guaranteed complete simply because a month has data.

Run focused importer, consumption, credential, API and model tests. CI runs the
full existing suite with PostgreSQL. Changes must remain unmerged until checks
and migration verification are reviewed.
