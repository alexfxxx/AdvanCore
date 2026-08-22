# ADR-003 — Local Agent Runner: Fail-Closed Permission Model and Replaceable Worker Adapter

## Status

Approved and implemented as part of TASK-005.

## Context

AdvanCore's intended development operating model is:

```
Alex (owner) -> ChatGPT (architect/controller/reviewer) -> GitHub (source of truth)
    -> Local Agent Runner -> Kimi Code (worker) -> tests/results -> GitHub -> review
```

Before this decision Alex manually copied instructions and results between
ChatGPT and Kimi. TASK-001 through TASK-004 established repository discovery,
tests, migrations, and persistence/service conventions. TASK-005 was chartered
to create the first safe local runner control plane so routine relay work can
be reduced while human control over high-impact actions is preserved.

The key risk is scope and authority: an early runner that can freely commit,
push, merge, reset, access secrets, or run production migrations would expand
agent authority faster than the governance model can review it.

## Decision

Adopt a small, local, fail-closed agent runner with a replaceable worker
adapter.

Key choices:

1. **Default to dry-run / planning.** The runner's default command inspects the
   repository, discovers the requested task, validates safety preconditions, and
   prints the worker instruction. It does not launch a worker or mutate state
   unless the caller explicitly requests execution.

2. **Fail-closed safety validation.** The runner stops if any precondition is
   not satisfied:
   - current branch must not be `main`,
   - working tree must be clean,
   - task status must be `READY` or `REWORK`,
   - the selected task file must exist and be unambiguous.
   Unknown or unsupported state also stops rather than being repaired or
   guessed.

3. **No autonomous high-impact actions in the foundation.** Commit, push,
   merge, deployment, destructive database operations, secret access, and
   compliance/commercial rule changes remain gated for explicit human approval.
   No merge command, forced checkout, reset, or force-push is implemented.

4. **Replaceable worker adapter.** Concrete worker invocation is hidden behind a
   small `WorkerAdapter` interface. Kimi Code is the first adapter and uses the
   documented `kimi --prompt <instruction>` non-interactive mode. Other workers
   can be added later without changing orchestration logic.

5. **Canonical bounded instruction.** The worker is given a short, predictable
   instruction that references `AGENTS.md` and the selected task file, includes
   the no-commit/no-push approval gate, and asks for a completion report and
   git status. The full task specification is not redundantly embedded.

6. **Explicit runner state model.** A `RunnerResult` captures task discovery,
   validation outcome, planned instruction, worker launch/completion state, and
   the awaiting-approval state. This makes the runner auditable and testable.

## Consequences

- The runner can safely be invoked to inspect and plan without risk of Git or
  worker side effects.
- Adding a new worker requires only a new adapter implementation; validation,
  discovery, and CLI logic remain unchanged.
- High-impact actions are never accidental: the caller must opt in to worker
  execution, and the worker itself is instructed not to commit or push.
- The first version is deliberately small and local; remote/cloud runners,
  multi-agent swarms, scheduling, and continuous monitoring are deferred.

## Alternatives considered

- **Direct Kimi invocation hard-coded throughout the runner.** Rejected: it
  couples orchestration policy to one tool and makes future worker changes
  invasive.
- **Allow execution on dirty working trees with auto-stash.** Rejected: it
  introduces recovery automation and ambiguity. A clean tree is required until a
  future task explicitly defines a safe exception.
- **Auto-commit/push after successful tests.** Rejected: successful tests do not
  equal review acceptance. Self-approval is explicitly out of scope.
- **Use a workflow orchestration framework (Temporal, Airflow, etc.).**
  Rejected: the current need is a local, understandable control plane, not a
  distributed workflow engine.

## Compliance / risks

- No production data, secrets, or production databases are accessed.
- No schema changes or migrations were introduced.
- The runner uses only safe, read-only Git commands in planning mode.
- Worker execution is opt-in and still leaves commit/push/merge gated.
