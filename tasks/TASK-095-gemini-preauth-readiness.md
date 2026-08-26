# TASK-095 — Gemini Pre-Authentication Readiness Gate

STATUS: REVIEW

## Objective

Make Gemini's remaining owner-present setup, evaluation, and activation gates
explicit without accessing Google, authenticating, probing an account, or
launching a process.

## Business context

The owner wants to handle Gemini authentication after this unattended batch.
AdvanCore must enter that session knowing exactly what can be done safely and
must not mistake a consumer subscription for worker entitlement or approval.

## In scope

- Add a vendor-neutral candidate readiness summary based on registry facts.
- Mark provider-surface selection, authentication, data terms, and billing as
  owner-required.
- Keep usage evidence, smoke evaluation, and activation blocked until setup.
- Show the checklist and next owner action in AI Center.
- Document the direct-owner authentication boundary.

## Out of scope

Google/Gemini access, login, OAuth, API keys, billing activation, installation,
network probes, worker launch, registry activation, database changes,
deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-095-gemini-preauth-readiness.md`
- `advancore/services/candidate_readiness_service.py`
- `advancore/pages/ai_center.py`
- `docs/runbooks/GEMINI_CANDIDATE_SETUP.md`
- `tests/test_candidate_readiness_service.py`
- `tests/test_ai_center_page.py`

## Database impact

None.

## Acceptance criteria

- [x] Gemini remains candidate, non-launchable, and absent from routing.
- [x] Subscription entitlement and billing are not inferred.
- [x] Owner-required and blocked follow-on checks are distinct.
- [x] No account probe, authentication, process, credential, or network action occurs.
- [x] AI Center shows the next owner-present action plainly.
- [x] Focused tests and `git diff --check` pass.
- [x] Completion report produced.

## Constraints

Credentials must be entered directly into the owner-selected provider surface,
never pasted into AdvanCore, a task file, chat prompt, or worker instruction.

## Owner decisions

Deferred to the next owner-present session: Gemini access surface, acceptable
data terms, entitlement/billing acceptance, and authentication.

## Completion report

### Implemented

Fail-closed Gemini pre-authentication checklist, AI Center panel, and setup
runbook.

### Files changed

Only the six allowed task, service, page, runbook, and test files.

### Database changes

None.

### Tests and results

Candidate readiness, AI Center, registry, candidate adapter, and governance
tests pass; `git diff --check` passes.

### Assumptions

The next setup session will occur with the owner present at the Mac.

### Risks / unresolved issues

The correct supported Gemini access surface and subscription entitlement remain
unknown until checked with the owner present.

### Decisions required

Owner must choose the surface and accept its data/billing terms before direct
authentication.

### Recommended next step

Run independent review of TASK-086 through TASK-095. After review, begin the
owner-present Gemini setup task without merging to `main`.
