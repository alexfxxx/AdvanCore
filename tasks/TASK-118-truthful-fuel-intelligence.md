# TASK-118 — Truthful Fuel Intelligence

STATUS: COMPLETE

## Objective

Connect the existing immutable fuel records to the dashboard fuel console and
show bounded operational summaries without inventing readings, currency,
efficiency, or missing evidence.

## Business context

The visual fuel console exists but intentionally has no operational source.
Fuel entries now provide recorded litres, optional total cost, and optional
odometer readings that can support transparent, limited intelligence.

## In scope

- A read-only fuel intelligence service over existing fuel entries.
- Recorded entry count, total litres, optional cost coverage and cost-per-litre,
  daily recorded-litre trend, and positive observed odometer distance.
- Explicit disclosure that fuel-entry currency and full-tank evidence are not
  captured, so currency-labelled totals and fuel efficiency are unavailable.
- Connect the governed service to the existing Plotly fuel console.
- Truthful connected, unavailable, and empty states.
- Focused service and presentation tests.

## Out of scope

- Forecasts, estimated fuel consumption, currency assumptions, profitability,
  emissions, external integrations, migrations, real data imports,
  credentials, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-118-truthful-fuel-intelligence.md`
- `advancore/services/fuel_intelligence_service.py`
- `advancore/pages/dashboard.py`
- `advancore/ui/fuel_trends.py`
- `advancore/ui/custom_components.py`
- `tests/test_fuel_intelligence_service.py`
- `tests/test_dashboard_visual_foundation.py`
- `tests/test_dashboard_page.py`

## Database impact

Read-only query of the existing `fuel_entries` table. No schema or data change.

## Acceptance criteria

- [ ] Empty records produce zero counts and explicit unavailable measures.
- [ ] Daily trend values are sums of recorded litres only.
- [ ] Cost summaries use only entries with recorded cost and never add a
      currency label.
- [ ] Odometer distance uses only positive consecutive differences per vehicle;
      ignored intervals are disclosed.
- [ ] Fuel efficiency is not calculated without full-tank evidence.
- [ ] Dashboard query failure produces a bounded unavailable state.
- [ ] Focused and full tests pass; Bugbot, CI, and GitGuardian are clean.

## Owner decisions

None. Adding currency and full-tank evidence would require later approved data
model decisions.

## Completion report

### Implemented

- Added a read-only fuel intelligence service using recorded entries only.
- Connected daily litre totals and bounded metrics to the existing Plotly fuel
  console.
- Added explicit currency, cost-coverage, odometer, efficiency, unavailable,
  and no-record disclosures.

### Files changed

- `tasks/TASK-118-truthful-fuel-intelligence.md`
- `advancore/services/fuel_intelligence_service.py`
- `advancore/pages/dashboard.py`
- `advancore/ui/fuel_trends.py`
- `advancore/ui/custom_components.py`
- `tests/test_fuel_intelligence_service.py`
- `tests/test_dashboard_visual_foundation.py`
- `tests/test_dashboard_page.py`

### Database changes

None.

### Tests and results

- Focused after independent-review repairs: `30 passed in 1.92s`.
- Full repository after independent-review repairs: `1223 passed, 2 skipped in
  181.90s`.
- `git diff --check`: passed.

### Assumptions

Positive odometer differences are reported only as observed distance, never as
proof of litres consumed over that distance.

### Risks / unresolved issues

Fuel efficiency and currency-specific reporting remain unavailable until the
data model captures sufficient governed evidence.

### Decisions required

None.

### Recommended next step

Perform final cross-task verification and rebuild the local Docker app only
after this task is integrated.
