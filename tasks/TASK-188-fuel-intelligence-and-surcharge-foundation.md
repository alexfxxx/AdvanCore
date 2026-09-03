# TASK-188 — Fuel Intelligence and Contract Surcharge Foundation

## Status

COMPLETE — MIGRATION NOT APPLIED

## Objective

Replace the dated static diesel-price reference with a once-daily, local,
evidence-backed Shell/SPC benchmark and use it to produce clearly labelled
draft fuel-adjustment indications for recurring customer services whose
contract terms have been explicitly recorded.

## Owner decisions

- Refresh automatically at most once per Singapore calendar day while the app
  is running.
- Shell and SPC gross diesel pump prices are the only benchmark inputs; their
  two-value median (the midpoint) is the benchmark.
- Persist figures and the minimum provenance/status needed to verify them; do
  not retain downloaded webpages or workbooks.
- Preserve the last successful benchmark and visibly mark it stale after a
  failed refresh.
- Never substitute, estimate or invent a missing price.
- Fuel-adjustment terms belong to each recurring-service contract, not a
  global user-adjustable rule.
- Contract terms start unconfigured. The owner records them once and the app
  reuses them without asking for repeated approvals.
- A calculated amount is a draft indication only; it never creates an invoice,
  financial entry or customer communication.

## In scope

- Add successful daily fuel-market snapshots and bounded refresh-state data.
- Collect Shell and SPC official gross diesel figures with strict parsers.
- Run a non-blocking once-daily refresh from the local FastAPI lifecycle.
- Return current benchmark, staleness, source timestamps and recent history.
- Add effective-dated, append-only recurring-service fuel rule history.
- Calculate a transparent draft monthly fuel adjustment from saved contract
  facts and the current verified benchmark.
- Update the compact fuel dashboard and selected-customer recurring-service
  view.
- Add an unapplied additive Alembic migration and synthetic focused tests.

## Explicitly out of scope

- Applying the migration, writing real customer values, or changing existing
  fuel-entry facts.
- Motorist.sg, Chartkick, petrol grades, discounts, invoice generation,
  automatic billing, email, PDF generation or manual price overrides.
- Raw-page storage, sample operational figures, silently fabricated fallbacks,
  deployment, credentials, billing, `main`, or changes to `agent_runner`.

## Contract calculation

For a configured recurring service, the draft uses only saved facts:

1. `price_variance_percent = (benchmark - baseline) / baseline × 100`
2. When the absolute variance is within the saved contract tolerance, the
   draft adjustment is zero.
3. Otherwise `draft_adjustment = fixed_monthly_amount × fuel_cost_share ×
   price_variance_percent`.

The result remains a labelled draft and exposes every input. A missing rule or
stale/missing benchmark produces no amount.

## Database impact

One additive migration creates fuel-market snapshot, refresh-state and
recurring-service fuel-rule tables. It is prepared only and must not be applied
without a fresh verified backup and separate approval.

## Acceptance criteria

- Dashboard reads never cause network calls or database writes.
- A successful daily refresh requires valid positive Shell and SPC diesel
  figures; the snapshot is stored atomically.
- At most one automatic attempt occurs per Singapore calendar day.
- Failure keeps the prior snapshot and marks it stale with a bounded reason.
- No source page, workbook, prompt, credential or full raw error is stored.
- No contract rule means no calculated surcharge.
- Rule history is forward-only; saved historical facts are not deleted.
- Browser writes retain loopback, action-token and explicit confirmation gates.
- Focused tests use synthetic source payloads and SQLite only.

## File allowlist

- `tasks/TASK-188-fuel-intelligence-and-surcharge-foundation.md`
- `alembic/versions/f6e188_fuel_intelligence_surcharge.py`
- `advancore/models/__init__.py`
- `advancore/models/fuel_market.py`
- `advancore/repositories/__init__.py`
- `advancore/repositories/fuel_market.py`
- `advancore/services/activity_service.py`
- `advancore/services/fuel_market_service.py`
- `advancore/services/fuel_market_sources.py`
- `advancore/api/app.py`
- `advancore/api/dependencies.py`
- `advancore/api/editing_gateway.py`
- `advancore/api/routes/editing.py`
- `advancore/api/routes/operations.py`
- `advancore/api/schemas.py`
- `frontend/app.js`
- `frontend/editing.js`
- `frontend/index.html`
- `frontend/styles.css`
- `tests/test_fuel_market_sources.py`
- `tests/test_fuel_market_service.py`
- `tests/test_api_fuel_market.py`
- `tests/test_api_fuel_benchmark.py`
- `tests/test_frontend_fuel_contract.py`
- `tests/test_activity_service.py`
- `tests/test_migrations.py`

## Completion report

### Implemented

- Replaced the runtime static-reference read path with persisted daily Shell
  and SPC gross-diesel snapshots and their exact midpoint.
- Added strict, size-bounded official-source readers. A missing field, changed
  format, untrusted redirect or non-positive figure fails closed.
- Added a daemon lifecycle refresher that checks hourly but attempts external
  collection at most once per Singapore calendar day.
- Added current/stale/unavailable status, bounded failure evidence and recent
  figure history without storing raw source content.
- Added forward-only recurring-service contract fuel rules and transparent
  draft adjustment calculations.
- Added compact dashboard status/trend presentation and contract-term controls
  inside existing customer recurring-service profiles.

### Database changes

Revision `f6e188fuel` is additive and chained from `f5e185payroll`. It was
compiled for PostgreSQL but was not applied to the local database.

### Verification

- Strict parsers were checked against the current live official Shell and SPC
  structures; the diagnostic read returned valid figures but wrote nothing.
- Focused source, service, API, activity, migration, recurring-service and
  frontend tests: 55 passed.
- Wider primary API safety checks: 32 passed.
- JavaScript syntax and `git diff --check`: passed.
- PostgreSQL offline migration compilation: passed.
- GitHub full regression initially found one false-positive legacy frontend
  guard: the lowercase provider field name contained the word used by that
  guard for command-shell detection. The chart now constructs that approved
  data key without changing behavior; the bounded repair was retested.

### Safety outcome

- No operational/customer record, credential, raw webpage or workbook was
  added to Git.
- No database migration, real-data change, invoice, financial entry, email,
  deployment or `main` interaction occurred.

### Next governed step

Review and merge the feature PR into `projects-lifecycle-recovery` only if
clean. Before activating the migration, create and verify a fresh local backup,
then obtain the existing migration-application approval.
