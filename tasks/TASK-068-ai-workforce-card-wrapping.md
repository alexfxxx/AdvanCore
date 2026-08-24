# TASK-068 — AI Workforce Card Wrapping

STATUS: REVIEW

## Objective

Make every AI Workforce role fully readable by wrapping long card values at
laptop and phone widths instead of clipping or truncating them.

## Business context

The owner approved the TASK-067 command-center design but reported that long
worker-role values, including the Kimi role, are cut off inside the large
cards. These values explain the governed worker route and must remain visible.

## Facts

- AI Workforce roles are rendered with Streamlit metric cards.
- The current theme does not override Streamlit's single-line metric-value
  behavior.
- This is a presentation defect; the worker route and authorization boundary
  must not change.

## In scope

- Allow metric values to wrap within their card at laptop and phone widths.
- Preserve the approved light command-center design and responsive stacking.
- Add a focused regression test for the wrapping rules.
- Verify the live dashboard at phone and laptop widths.

## Out of scope

- Worker routing, authorization, credentials, quotas, usage policy, business
  rules, provider registration, database changes, or `main`.
- Redesigning the approved command center.

## Allowed changed-file scope

- `tasks/TASK-068-ai-workforce-card-wrapping.md`
- `advancore/ui/theme.py`
- `tests/test_theme.py`

## Database impact

None.

## Acceptance criteria

- [x] Long AI Workforce role values wrap and remain fully readable.
- [x] Metric cards keep the approved light visual design.
- [x] The dashboard remains usable at phone and laptop widths.
- [x] Focused and full tests pass.
- [x] Completion report produced.

## Test requirements

- Add assertions covering normal white-space, visible overflow, and safe word
  wrapping for metric values.
- Run the focused theme test, the full repository suite, and `git diff --check`.
- Inspect the running dashboard at phone and laptop widths.

## Constraints

- Keep the change local and dependency-free.
- Do not change worker authority or the Kimi-first/Codex-fallback route.
- Do not add external scripts, assets, or credentials.

## Owner decisions

The owner approved the command-center design and explicitly requested this
text-wrapping repair on 24 August 2026.

## Completion report

### Implemented

- Overrode Streamlit's nested metric-value truncation rules at the value,
  Markdown container, and paragraph layers.
- Enabled normal white-space, visible overflow, clipped rather than ellipsized
  text, and safe anywhere wrapping.
- Preserved the approved card styling and allowed each card to grow to contain
  every wrapped line.

### Files changed

- `tasks/TASK-068-ai-workforce-card-wrapping.md`
- `advancore/ui/theme.py`
- `tests/test_theme.py`

### Database changes

None.

### Tests and results

- Focused theme tests: 3 passed.
- Full repository suite: 926 passed in 179.54 seconds.
- `git diff --check`: passed.
- Live laptop-width inspection at 1280 × 720 confirmed no ellipsis on any of
  the six AI Workforce values and confirmed every value remained fully inside
  its card.
- The existing 900 px and 640 px responsive rules and phone-width stacking
  regression assertions remain in place.

### Assumptions

- The existing responsive layout remains the approved phone behavior; this
  repair changes only nested metric text behavior.

### Risks / unresolved issues

- The currently open app on port 8501 is the prior integrated build. The
  repaired feature branch was verified separately on local test port 8502 and
  will appear on the normal app after integration and restart.

### Decisions required

None.

### Recommended next step

- Publish the feature branch for independent review and integrate it only into
  `projects-lifecycle-recovery` after checks pass.
