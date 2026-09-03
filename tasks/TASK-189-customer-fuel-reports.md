# TASK-189 — Customer Fuel Reports

## Status

COMPLETE

## Objective

Add a dedicated, local, read-only Fuel Reports screen that turns the existing
verified Shell/SPC benchmark and saved recurring-service fuel terms into a
transparent customer-facing draft report.

## Owner decisions

- Provide a dedicated Fuel Reports screen rather than another long dashboard
  segment.
- Filter by customer, recurring service and benchmark evidence date range.
- Support on-screen review, browser Print / Save as PDF, and CSV download.
- Use only verified Shell/SPC figures and saved contract terms.
- Do not create invoices, financial entries, emails, customer messages or
  automatic submissions.
- Do not invent customers, services, contract terms, prices or missing values.

## In scope

- Serve a same-origin `/fuel-reports` page from the existing FastAPI app.
- Add an entry point from the primary CSS console.
- Load existing customers, their recurring services, the selected service's
  fuel-adjustment draft, and the persisted market benchmark/history.
- Keep report generation entirely read-only and visibly label all calculated
  amounts as draft indications.
- Filter stored benchmark evidence using an owner-selected date range.
- Export only the currently reviewed report to CSV or browser print/PDF.
- Preserve the user's allowlisted local display theme when available.
- Add synthetic contract/API tests; do not create real records.

## Explicitly out of scope

- Database or Alembic changes, live-data imports, sample customer data,
  invoice generation, email, automatic customer delivery, approval workflows,
  manual fuel-price overrides, deployment, credentials, billing, `main`, or
  changes to `agent_runner`.

## Safety rules

- Report data comes only from existing same-origin API responses.
- Missing customers, services, contract terms, or verified benchmark evidence
  produces a clear unavailable state, never a fabricated result.
- CSV fields are escaped and spreadsheet-formula prefixes are neutralised.
- The dedicated page and its operational API reads retain loopback controls,
  strict CSP, and `Cache-Control: no-store`.
- Printing/exporting is an explicit local owner action.

## Acceptance criteria

- `/fuel-reports` opens as a dedicated responsive page from the main console.
- No customer or no recurring service is handled without an exception or
  invented placeholder record.
- A selected configured service displays customer, service, current benchmark,
  saved contract inputs, formula result and selected evidence history.
- Stale/unavailable benchmarks or missing terms never present an adjustment as
  ready.
- Print/PDF and CSV controls remain disabled until a report is generated.
- No write API, action token, network host, remote script or automatic export is
  used by the reporting client.

## File allowlist

- `tasks/TASK-189-customer-fuel-reports.md`
- `advancore/api/app.py`
- `advancore/api/routes/operations.py`
- `advancore/services/fuel_market_service.py`
- `frontend/index.html`
- `frontend/fuel-reports.html`
- `frontend/fuel-reports.js`
- `frontend/styles.css`
- `tests/test_api_console.py`
- `tests/test_api_editing.py`
- `tests/test_api_fuel_benchmark.py`
- `tests/test_fuel_market_service.py`
- `tests/test_frontend_fuel_reports.py`
- `tests/test_frontend_workspace_contract.py`
- `tests/test_frontend_editing_contract.py`

## Database impact

None.

## Completion report

### Implemented

- Added a dedicated `/fuel-reports` screen linked from the primary CSS console.
- Added saved-customer and non-archived recurring-service selection, an evidence
  date window, transparent contract/calculation fields, verified source cards,
  and stored benchmark history.
- Added explicit local Print / Save-as-PDF and CSV actions. CSV output escapes
  quotes and neutralises spreadsheet-formula prefixes.
- Added request-generation and identity guards so delayed responses cannot mix
  one customer's report with another customer's service.
- Refetches benchmark evidence during generation and refuses mismatched or newly
  stale evidence before rendering or enabling exports.
- Extended loopback and no-store protection to the page, customer register and
  benchmark reads. Archived services are also rejected by the service layer.

### Files changed

Only files in the TASK-189 allowlist were changed.

### Database changes

None. No migration or operational record was created, updated or deleted.

### Tests executed

- Focused API/frontend/fuel safety suite: 47 passed.
- Full isolated SQLite regression: 1,661 passed, 2 skipped.
- JavaScript syntax and Git whitespace checks: passed.
- Bugbot review after two bounded repair cycles: clean.

### Assumptions

- Browser Print / Save as PDF is the approved first PDF path; AdvanCore does not
  render or store a server-side PDF.
- The selected date range filters the source-evidence history. The draft amount
  remains tied to the current verified benchmark returned by the existing fuel
  adjustment service.

### Risks / unresolved issues

- No current customer record exists in the local database, so runtime visual
  verification can exercise the correct empty state but not a real customer
  report without owner-approved customer and contract data.
- The existing third-party `httpx` compatibility warning remains unchanged.

### Decisions required

None for this task.

### Recommended next step

Merge the clean PR into `projects-lifecycle-recovery`, restart the port-8000
app, and visually verify the dedicated empty-state page. Add a real customer
and recurring-service contract only when the owner is ready to enter those
facts locally.
