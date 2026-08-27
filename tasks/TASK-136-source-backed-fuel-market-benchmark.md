# TASK-136 — Source-Backed Fuel Market Benchmark

STATUS: READY

## Objective
Add a dated, pre-discount Singapore pump-price benchmark beside existing truthful fuel intelligence.

## Facts
- Motorist Singapore lists cross-market pump prices and trends.
- SPC publishes official pre-discount SGD/litre prices.
- Shell publishes an official dated price-board workbook and defines gross price as pump price before discounts.

## In scope
- Read-only source snapshot dated and retrieved on 28 August 2026.
- Motorist market comparison plus official SPC and Shell gross prices.
- Pre-discount diesel benchmark with source URLs, provider dates, retrieval date, and staleness warning.
- Existing recorded Fleet fuel summaries; no invoice or charging assumptions.

## Out of scope
- Web scraping during normal app startup, discount calculations, forecasts, automatic database writes, estimates, or electricity charging.

## Database impact
None.

## Allowed changed-file scope
- `advancore/reference_data/fuel_market_sg_2026-08-28.json`
- `advancore/api/**`
- `frontend/**`
- `tests/test_api_fuel_benchmark.py`
- `tests/test_frontend_fuel_contract.py`
- `docs/sources/FUEL_MARKET_BENCHMARK.md`
- This task file

## Acceptance criteria
- [ ] All prices are SGD/litre before discounts and have auditable sources.
- [ ] Market diesel low/high/median are calculated from the recorded comparison values.
- [ ] Stale observations are labelled, not silently called live.
- [ ] No invented fuel or business figures appear.

## Owner decisions
None; sources and pre-discount definition were specified by the owner.

## Completion report
Pending.
