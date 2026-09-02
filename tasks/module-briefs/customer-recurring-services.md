# Customer Recurring Services — Business Module Brief

STATUS: APPROVED

MODULE_ID: customer_recurring_services

## Module identity

Customer Recurring Services is a customer-profile segment within Transport
Operations. It records a customer's agreed repeating route, operating schedule,
ordered stops, vehicle requirement and fixed monthly rate. It is not a new
top-level module and does not replace the dated Trip register.

## Business problem

Recurring customer routes currently cannot be represented without either
duplicating the same information into many dated Trips or losing the agreed
tender schedule. The owner needs one stable service definition inside the
customer profile that can later feed daily operations while preserving its fixed
monthly commercial basis.

## Facts

- FACT: The owner's customer routes recur on operating days agreed in a tender.
- FACT: Each recurring route is priced at a fixed monthly amount.
- FACT: The monthly amount is not recalculated from trips, operating days or
  calendar days.
- FACT: Operating days do not change until a later agreement replaces them.
- FACT: Ad-hoc services are separate one-off trips.
- FACT: Recurring services must appear inside the customer's profile rather than
  as a separate visible Contract module.
- FACT: A dated Trip is an actual operational journey and is not the source
  definition for a recurring service.
- FACT: Real customer schedules and prices belong only in local PostgreSQL and
  local protected backups, never in GitHub.

## Required fields

Each recurring service requires only:

- its customer;
- an owner-entered service reference;
- its existing Route record;
- the agreed operating weekdays;
- an ordered list of named stops with scheduled times;
- the tender-stated vehicle requirement as bounded source text;
- the fixed monthly amount and three-letter currency code;
- an effective start date and optional effective end date; and
- active, paused or archived status.

An optional replacement link may connect a new service version to the archived
version it replaces. No daily rate, trip count, expected monthly mileage,
discount, tax amount or invoice total belongs in this record.

## Reference sources

- The accepted customer tender, quotation or schedule is the authority for
  operating days, stop order, times, vehicle requirement and fixed monthly rate.
- The existing Customer and Route registers provide the internal relationships.
- Owner entry or a separately approved preview-first import is the only initial
  publication method.
- Source workbooks and PDFs remain private and are never copied into GitHub.

## Calculations

None. The fixed monthly amount is displayed as entered. It is not divided by
operating days, expanded into daily revenue, adjusted for public holidays or
treated as an invoice or GST calculation.

## Workflows and approvals

- The owner opens a customer and views its Recurring Services segment.
- The owner can create a service from confirmed tender information, pause it,
  archive it or prepare a forward replacement for a later agreement.
- Normal in-contract schedule or price changes are not silently overwritten. A
  changed agreement archives the previous version and creates a new effective
  version so the former facts remain understandable.
- A later daily-planning task may generate dated Trips from active service
  definitions. That later automation requires its own planning-horizon,
  duplicate and exception rules and is not authorised here.
- Ad-hoc services continue through the one-off Trip workflow.

## Imports

Future customer schedule imports must use a preview-first boundary. The preview
must identify the customer, route, operating days, ordered stops and times,
vehicle requirement, fixed monthly amount and effective period; disclose missing
or conflicting values; and write nothing until separately approved. Publication
must be one local transaction with rollback on failure. No source file or real
row is stored in Git.

## Reports and filters

The customer profile may list current, paused and archived recurring services.
The compact list should show service reference, route, operating days, first and
last scheduled times, vehicle requirement, fixed monthly amount and status. A
selected service may show its ordered stops and effective dates. Cross-customer
profitability, invoice reporting and predicted daily revenue are deferred.

## Database impact

A later proposal may add one recurring-service table and normalized child rows
for operating weekdays and ordered timed stops. All structures must be additive,
link to the existing Customer and Route tables, preserve current rows and use an
Alembic migration. Approval of this brief does not authorise implementation,
migration creation, migration application or data import.

## Security and compliance

Customer names, locations, schedules and prices are business-sensitive. They
remain in local PostgreSQL and protected local backups. GitHub may contain only
schema, code and synthetic test fixtures. A schedule must not contain passenger
or employee personal data unless a later approved purpose and access boundary
requires it. No AI worker may transmit the private source documents or extracted
records to a third-party service without explicit owner approval.

## Owner decisions

None

## Acceptance examples

- Normal: a Monday-to-Friday route with several timed pickup stops appears once
  under its customer with one fixed SGD monthly amount.
- Normal: a later agreement changes a time or price; the former service is
  archived and the replacement starts on its approved effective date.
- Normal: pausing a service does not change or prorate its stored monthly amount.
- Boundary: a public holiday does not cause AdvanCore to invent a daily
  deduction or recalculate the fixed monthly amount.
- Boundary: an ad-hoc Saturday request is created as one dated Trip and does not
  alter the recurring service.
- Invalid: attempting to save a recurring service without a customer, route,
  operating day, stop schedule, monthly amount or effective start date fails
  before any partial write.
- Invalid: importing a real workbook directly into Git or tests is prohibited.
