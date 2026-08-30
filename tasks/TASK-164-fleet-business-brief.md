# TASK-164 — Fleet Business Brief

STATUS: COMPLETE

## Objective

Consolidate the owner's previously approved Fleet facts and the existing Fleet
implementation into one reviewable business-module brief, while leaving every
unresolved commercial rule explicitly owner-controlled.

## Business context

The local Fleet register already contains the approved 27-vehicle import and
supports legal-owner grouping, exact seating, vehicle details and current cost
fields. The next Fleet increment must start from the owner's real requirements,
not from AI-generated columns or assumed calculations.

## Facts

- The owner selected Fleet Management as the first post-core business module.
- TASK-119 and TASK-123 through TASK-125 established and verified the current
  Fleet identity, filtering, import and recovery foundation.
- Hire-purchase information and its calculation rules were deliberately
  deferred from the existing Fleet schema.

## In scope

- Review the current Fleet model, services, screens, API and completed task
  records.
- Create a Fleet business brief using only confirmed requirements.
- Separate existing capabilities from proposed additions.
- Record the exact owner decisions required before implementation.

## Out of scope

- Code, schema, migration, live-database or real-data changes.
- Re-importing or correcting any of the 27 vehicle records.
- Deciding finance formulas, compliance rules or reports on the owner's behalf.
- Fuel, electric charging, drivers, dispatch, maintenance, authentication,
  deployment, credentials, billing or `main`.

## Allowed changed-file scope

- `tasks/TASK-164-fleet-business-brief.md`
- `tasks/TASK-165-fleet-hire-purchase-schema-proposal.md`
- `tasks/module-briefs/fleet-management.md`

## Database impact

None.

## Acceptance criteria

- [x] Existing Fleet functionality is distinguished from proposed additions.
- [x] Every stated fact is traceable to an owner decision or repository record.
- [x] Missing finance and reporting rules remain explicit owner decisions.
- [x] The business brief remained fail-closed until the owner approved all six
      recorded decisions, then passed the implementation-readiness gate.
- [x] No source PDF, real Fleet payload or personal/business value is added.
- [x] The post-programme module-design gate is declared explicitly.
- [x] Brief/readiness validation and repository diff checks pass.

## Test requirements

- Evaluate the brief with the read-only module brief validator and confirm that
  it is structurally complete but not implementation-ready while decisions
  remain.
- Run the focused module-design service tests.
- Run `git diff --check`.

## Constraints

- `agent_runner` remains the authority boundary.
- The brief is a design artifact, not migration or implementation authority.
- Unknown values remain unknown; no amount, date, status or compliance rule may
  be inferred.
- GitHub remains the code and governance source of truth. PostgreSQL remains the
  operational-data source of truth.

## Module design gate

Classification: NON_MODULE
Module identifier: None
Approved brief: None

## Owner decisions

None for producing this bounded draft. The unresolved Fleet business decisions
are listed in `tasks/module-briefs/fleet-management.md` and must be resolved
before that brief can be approved.

## Completion report

### Implemented

- Added a fact-based Fleet business brief covering the existing register,
  proposed hire-purchase extension, workflows, imports, reports and boundaries.
- Kept the brief fail-closed as a draft with explicit owner decisions, then
  recorded the owner's approval of all six recommended choices.

### Files changed

- `tasks/TASK-164-fleet-business-brief.md`
- `tasks/TASK-165-fleet-hire-purchase-schema-proposal.md`
- `tasks/module-briefs/fleet-management.md`

### Database changes

None.

### Tests and results

- Before approval, the read-only evaluator found every required section, no
  placeholder content and no duplicated section, and correctly returned
  `ready=False` while owner decisions remained.
- After approval, the evaluator found every required section, 16 confirmed
  fact lines, no placeholders or duplicates, no unresolved decisions, and
  returned `ready=True`.
- The TASK-165 business-module gate passed against the approved Fleet brief.
- The TASK-164 module gate passed as an explicit non-module design task.
- Focused module-design tests: 14 passed.
- `git diff --check`: passed.

### Assumptions

None. Proposed finance and reporting choices are not treated as facts.

### Risks / unresolved issues

Approval of the brief authorises bounded planning only. It does not authorise a
migration, live-database write or implementation.

### Decisions required

None for TASK-164. TASK-165 remains a separately reviewed proposal.

### Recommended next step

Review and approve or reject the TASK-165 minimum schema proposal before any
implementation or migration work begins.
