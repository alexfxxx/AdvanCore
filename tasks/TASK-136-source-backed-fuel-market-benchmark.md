# TASK-136 — Source-Backed Fuel Market Benchmark

STATUS: COMPLETE

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
- [x] All prices are SGD/litre before discounts and have auditable sources.
- [x] Market diesel low/high/median are calculated from the recorded comparison values.
- [x] Stale observations are labelled, not silently called live.
- [x] No invented fuel or business figures appear.

## Owner decisions
None; sources and pre-discount definition were specified by the owner.

## Completion report
Stored a dated, auditable reference snapshot separate from operational fuel
records. Motorist supplies the five-provider diesel comparison; official SPC
and Shell rates retain their provider timestamps. The API calculates SGD
3.89/L low, SGD 3.95/L median and SGD 4.05/L high. The UI explicitly labels
official checks as dated rather than live. Verified on 28 August 2026.
