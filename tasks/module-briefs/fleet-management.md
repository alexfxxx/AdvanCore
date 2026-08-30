# Fleet Management — Business Module Brief

STATUS: APPROVED

MODULE_ID: fleet_management

## Module identity

Fleet Management is the owner-operated register for vehicles used across the
owner's different registered companies. Its first boundary is vehicle identity,
legal ownership, approved logcard details, current recurring costs and bounded
hire-purchase visibility. Drivers, routes, trips, fuel, workshop charging,
maintenance and accounting ledgers remain separate modules.

## Business problem

The owner needs one reliable place to see which company owns each vehicle, the
vehicle's exact characteristics, its current fixed costs and any remaining
scheduled hire-purchase commitment. The existing register covers identity and
current parking, insurance and road-tax values, but hire-purchase fields and
their business calculation have not been approved or implemented.

## Facts

- FACT: The local operational database contains an owner-approved import of 27
  unique vehicles grouped under three registered owners.
- FACT: The approved import contains 26 buses and one lorry; real row values and
  source logcards are not stored in Git.
- FACT: A vehicle may be registered to a company other than Advan.
- FACT: Vehicle type and exact passenger capacity are separate values and
  separate filters; capacity must never be inferred from model wording.
- FACT: Approved vehicle types are Bus, lorry and car.
- FACT: Exact seating values are stored as source-backed numbers rather than
  approximate seating bands.
- FACT: Parking requires current provider, location and GST-inclusive monthly
  cost; no parking agreement or history is required.
- FACT: Insurance requires only the current provider and GST-inclusive annual
  amount; insurance history is not required.
- FACT: Road tax requires the current amount and a 6- or 12-month period. Local
  renewal is paid by GIRO, and no amount may be inferred from vehicle capacity.
- FACT: Unknown values remain null and appear as `Not recorded`.
- FACT: Diesel purchasing and workshop electric charging are separate, deferred
  areas and must not be folded into this Fleet slice.
- FACT: The owner wants finance company, loan amount when available, monthly
  instalment and automatically calculated remaining scheduled payments for
  vehicles under hire purchase.
- FACT: The owner approved loan start date plus total loan months as the source
  for the monthly remaining-payment countdown.
- FACT: The owner approved display of both remaining scheduled payment count
  and projected remaining scheduled amount.
- FACT: Official lender settlement balance, finance columns in the compact
  Fleet list, combined monthly fixed-cost reporting and CSV export are deferred.
- FACT: The owner approved browser-local display controls that allow approved
  Fleet detail fields to be shown, hidden and reordered by dragging.
- FACT: The application is currently used by one local owner; public access and
  multi-user approvals are not part of this module stage.

## Required fields

Existing approved vehicle identity and detail fields:

- registration number as the unique vehicle identity;
- registered owner/company;
- make/model and manufacture year;
- vehicle type and exact LTA passenger capacity;
- propellant, scheme, chassis number, engine number, original registration
  date, lifespan expiry, COE expiry, primary colour, unladen weight and maximum
  laden weight;
- active vehicle status;
- current parking provider, location and GST-inclusive monthly cost;
- current insurance provider and GST-inclusive annual amount; and
- current road-tax amount and its 6- or 12-month period.

Approved hire-purchase information:

- finance company, when applicable;
- original loan amount, when known;
- monthly instalment;
- loan start date; and
- total loan term in months.

Remaining scheduled payment count and projected remaining scheduled amount are
derived display values and must not be persisted as independent source values.

No other Fleet field is authorised by this brief.

## Reference sources

- LTA vehicle logcard: registration identity, registered owner and approved
  vehicle/logcard characteristics.
- Finance agreement or current lender statement: finance company, original loan
  amount, instalment, duration and any lender-reported balance.
- Current operator payment record: parking provider, location and monthly
  GST-inclusive amount.
- Current insurance policy or invoice: insurer and annual GST-inclusive amount.
- Current LTA/GIRO record: road-tax amount and 6- or 12-month period.
- Owner entry remains the initial data-entry method. No automatic provider,
  lender or government integration is approved for this stage.

## Calculations

- Scheduled payment number one falls one calendar month after the loan start
  date; later payments follow monthly through the total term. If a target month
  has no matching day, its last calendar day is used.
- `elapsed scheduled payments` is the number of those payment dates on or
  before the calculation date, limited to the range from zero to total loan
  term months.
- `remaining scheduled payments` equals total loan term months minus elapsed
  scheduled payments and cannot be below zero.
- `projected remaining scheduled amount` equals remaining scheduled payments
  multiplied by monthly instalment and is rounded to two decimal places.
- A calculated remaining scheduled amount must not be described as an official
  lender settlement balance. Official settlement balance is deferred and is
  not stored in this increment.
- Missing finance inputs must produce `Not recorded`, not zero or an estimate.
- Parking is already a GST-inclusive monthly value; insurance is already a
  GST-inclusive annual value; road tax is a current 6- or 12-month value.
- Combined monthly Fleet-cost calculation is deferred.

## Workflows and approvals

- The owner can add a registered company, add a vehicle, select a vehicle and
  update approved details on the Fleet screen.
- The owner can filter the same Fleet screen by company, vehicle type and exact
  passenger capacity, individually or together.
- In the decoupled local console, the owner can show, hide and reorder approved
  selected-vehicle detail fields. Dragging changes presentation only and must
  never change a saved vehicle value.
- Display order and visibility persist on the same browser/device and can be
  reset to the approved default. Actual field values continue to be changed
  only through the governed Fleet edit form.
- Company grouping and vehicle details must use saved operational data only.
- A missing optional value remains visible as `Not recorded`.
- Future bulk imports must stop at a preview and duplicate check before any
  operational write. Publication requires explicit owner approval and one
  transaction with rollback on failure.
- No automatic deletion, ownership transfer, finance reconciliation or
  compliance decision is approved.

## Imports

- CSV or document-derived imports may be supported through the existing
  preview-first import boundary.
- Registration number is the duplicate identity for vehicles. Company names
  must use normalized exact matching through the existing legal-owner service.
- An import preview must show only approved Fleet fields, disclose conflicts and
  preserve unknowns as null.
- Source PDFs and unnecessary owner identifiers or addresses must not be copied
  into Git or stored as Fleet records.
- Real-data publication remains a separately approved action after preview.

## Reports and filters

Already approved:

- one Fleet screen grouped and filterable by registered company;
- separate vehicle-type and exact-passenger-capacity filters;
- a vehicle list showing registration number, company, make/model, type, exact
  seats and status; and
- a selected-vehicle detail view showing approved logcard and current-cost
  values.

Approved addition:

- show finance company, original loan amount, monthly instalment, loan start
  date, total term, remaining scheduled payments and projected remaining
  scheduled amount only in the selected-vehicle detail view.

The compact Fleet list is unchanged. Finance list columns, a combined totals
summary and CSV export are deferred.

Approved selected-vehicle detail fields may be shown, hidden and reordered in
the decoupled console. Registration number and vehicle status remain pinned as
the vehicle identity. The preference stores only allow-listed field identifiers
and order, never operational values.

## Database impact

The existing `legal_entities` and `vehicles` structures already hold the
approved identity, logcard and current-cost fields. A later implementation may
propose only nullable finance company, original loan amount, monthly instalment,
loan start date and total loan term fields. Any schema change must be additive,
use Alembic, preserve all 27 vehicles, and require a fresh verified backup
before application. Approval of this brief does not authorise a migration.

## Security and compliance

Vehicle chassis and engine numbers and company ownership are business-sensitive
records and should remain local to the governed application and backup system.
Source documents may contain owner identifiers and addresses that are not
needed by Fleet and must not be imported. No credentials, bank-login details or
full finance documents should be stored in Fleet. Singapore LTA, finance, GST
or accounting meaning must be professionally or owner verified rather than
invented by an AI worker.

Browser-local display preferences may contain only approved field identifiers,
visibility and order. They must not contain vehicle values, arbitrary HTML,
scripts, CSS or server credentials.

## Owner decisions

None

## Acceptance examples

- Normal: a 43-seat bus linked to Company A appears under Company A and under
  the exact `43` filter; no approximate seating group is created.
- Normal: a vehicle without recorded insurance, parking or finance values shows
  `Not recorded` and contributes no invented amount to any display.
- Normal: a hire-purchase vehicle displays its lender and monthly instalment;
  remaining scheduled payments appear only when all owner-approved calculation
  inputs are present.
- Normal: the owner moves `Monthly instalment` ahead of `Parking`, hides
  `Primary colour`, refreshes the browser and sees the same safe layout.
- Boundary: resetting Fleet display restores the approved field order without
  changing any vehicle record.
- Boundary: a current road-tax amount is accepted only with a period of 6 or 12
  months; a standard amount is never assigned from seating capacity.
- Invalid: a second import row with the same normalized registration number is
  rejected before publication, and the database remains unchanged.
- Invalid: a finance document containing account credentials or unrelated
  personal identifiers is not stored or copied into the repository.
