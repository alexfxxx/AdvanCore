# TASK-055 — CI Portability Repair

STATUS: REVIEW

## Objective

Repair the three cross-platform failures exposed by PR #5 so the complete test
suite behaves consistently on the owner's Mac and GitHub's Linux runner.

## In scope

- Preserve task filename case when an exact filename is supplied and keep task
  lookup inside the canonical tasks directory.
- Make the Kimi planner test explicitly provide its mocked Mac isolation seam
  instead of depending on the host operating system.
- Give every controller handoff artifact a collision-resistant filename even
  when two handoffs are created within the same second.
- Add focused regression coverage and rerun the complete suite.

## Out of scope

Business behavior, credentials, provider policy, approval boundaries, worker
permissions, merge, `main`, deployment, production, data migration, or test
exclusions.

## Allowed changed-file scope

- `tasks/TASK-055-ci-portability-repair.md`
- `advancore/agent_runner/task.py`
- `advancore/agent_runner/controller_handoff.py`
- `tests/test_agent_runner.py`
- `tests/test_goal_task.py`
- `tests/test_controller_handoff.py`
- `tests/test_owner_action_orchestration_e2e.py`

## Owner decisions

None. The owner explicitly approved TASK-055 on 24 August 2026.

## Completion report

### Implemented

- Preserved exact task filenames on case-sensitive systems and rejected task
  traversal or symlink escape outside the canonical tasks directory.
- Made the Kimi planner test explicitly mock the required Mac isolation probe;
  production isolation remains mandatory and unchanged.
- Added microseconds and the unique handoff request identifier to controller
  handoff filenames so rapid successive handoffs cannot overwrite one another.

### Database changes

None.

### Tests executed and results

- Affected agent-runner, goal-task, handoff and owner-action suites: 155 passed.
- Full local repository suite: 867 passed.
- Python compilation and `git diff --check`: passed.

### Decisions required

- PR #5 merge remains a manual owner decision.
