# TASK-022 — Governed Worker Fallback Boundary

STATUS: READY

## Objective

Add a provider-neutral, explicitly configured implementation-worker fallback
boundary so an approved Codex CLI worker or another registered worker can
continue a governed task when Kimi is unavailable, without weakening
`agent_runner`, silently changing providers, or granting any worker controller
authority.

## Business context

TASK-021 proved the end-to-end orchestration architecture and also exposed an
operational dependency: Kimi quota exhaustion stopped implementation even
though an approved local Codex CLI worker was available. The owner has approved
support for Codex or another approved worker as a fallback.

AdvanCore must remain vendor-neutral. Fallback belongs in the permanent worker
adapter/orchestration boundary, while Codex desktop remains an optional local
execution environment. GitHub remains source-of-truth and `agent_runner`
remains the enforcement authority.

## Facts

- `WorkerAdapter` is the existing replaceable implementation boundary.
- Kimi and Kimi-Swarm adapters already use argv-based non-interactive execution.
- Codex CLI is locally available and exposes non-interactive `codex exec` with
  repository-root selection, `workspace-write` sandboxing, explicit approval
  policy, ephemeral sessions, and structured output.
- TASK-017/TASK-018 independently verify branch, HEAD, staging, tests, diff, and
  exact allowed changed-file scope after every worker attempt.
- Worker success is evidence only; controller approval remains separate.

## In scope

1. Add a `CodexWorkerAdapter` implementing the existing `WorkerAdapter`
   interface.
2. Invoke Codex with a fixed argv policy equivalent to:
   - `codex exec` non-interactive mode;
   - `--ephemeral`;
   - `--sandbox workspace-write`;
   - `--ask-for-approval never` so requests outside the sandbox fail rather
     than being escalated interactively;
   - `--cd <verified repository root>`;
   - bounded prompt passed as one argv value or stdin, never shell interpolation;
   - optional structured output only when parsing is required.
3. Explicitly prohibit Codex flags that bypass governance, including
   `--dangerously-bypass-approvals-and-sandbox`, danger-full-access, additional
   writable directories, remote/cloud execution, web search, and arbitrary
   config overrides.
4. Extend the canonical worker instruction so Codex and every future adapter
   receive the same task path, exact allowed changed-file scope, role limits,
   and prohibitions as Kimi-Swarm.
5. Add a fixed, code-owned registry of approved adapter names. Initial names may
   include `dry-run`, `kimi`, `kimi-swarm`, and `codex`.
6. Do not accept an arbitrary executable path, shell command, command template,
   environment assignment, or user-supplied argv as a worker adapter.
7. Add an explicit ordered worker policy, for example:
   `--worker kimi-swarm --fallback-worker codex`. Default remains one worker
   with no fallback.
8. Persist the selected primary and fallback worker names in orchestration
   checkpoints and consolidated artifacts.
9. Fallback must never be silent. Reports must identify attempted worker,
   classified failure, integrity checks, selected fallback, and terminal worker.
10. Permit fallback only for a bounded provider-availability classification,
    such as executable unavailable, provider quota/capacity/rate-limit, or
    provider authentication unavailable.
11. Before fallback, independently verify that the failed worker attempt:
    - did not change branch or HEAD;
    - did not stage any path;
    - did not modify or create repository files;
    - did not alter remotes;
    - produced no ambiguous or destructive state.
12. Any repository mutation, test failure, diff failure, scope failure, worker
    implementation error, timeout with uncertain child-process state, malformed
    output, or unknown failure is not a provider fallback condition. Preserve
    existing bounded repair/non-repairable behavior.
13. Use deterministic bounded failure classification. Do not persist full
    stdout/stderr, prompts, transcripts, credentials, or environment dumps.
14. Codex worker authentication remains external local configuration. AdvanCore
    must not read, write, display, refresh, or store Codex credentials.
15. Codex must remain implementation-worker-only and cannot record controller
    decisions, transition `DRAFT -> READY`, approve its own work, finalize,
    commit, push, merge, or deploy.
16. Update TASK-021 orchestration to accept and persist the explicit fallback
    worker while continuing to delegate execution/verification to the existing
    auto-pipeline.
17. Add CLI support to `auto` and `orchestrate` for an optional registered
    fallback worker. Reject duplicate, unknown, dry-run fallback, or unsafe
    combinations fail-closed.
18. Add deterministic tests for Codex argv safety, registry validation,
    provider-failure classification, clean-state fallback, mutation blocking,
    no silent fallback, checkpoint persistence/resume, exact scope, bounded
    evidence, and controller-role separation.
19. Update architecture documentation and add ADR-022.
20. Run the full pytest suite and complete this task report.
21. Stop at controller review without staging, committing, pushing, merging, or
    deploying TASK-022.

## Important governance rule

**Fallback changes implementation capacity; it never changes authority.**

No adapter or fallback policy may:

- infer approval from worker output or passing tests;
- continue after repository mutation by a failed primary worker;
- use unrestricted/dangerous permission bypass modes;
- execute an arbitrary user-supplied command;
- broaden task scope or writable roots;
- expose credentials, secrets, production data, or unrestricted transcripts;
- stage, commit, push, merge, deploy, or touch `main`;
- silently choose a provider not explicitly configured and registered.

## Explicitly out of scope

- Planner fallback or controller fallback.
- Remote/cloud Codex execution.
- Codex SDK or OpenAI API integration.
- Arbitrary external-command plugins.
- Dynamic plugin installation or network-downloaded worker code.
- Automatic credential login or quota purchasing.
- Unlimited fallback chains; TASK-022 allows at most one fallback worker.
- Automatic controller decisions, merge, deployment, releases, or production
  access.

## Allowed changed-file scope

The TASK-022 implementation worker may change only these nine paths:

1. `advancore/agent_runner/worker.py`
2. `advancore/agent_runner/auto_pipeline.py`
3. `advancore/agent_runner/orchestration.py`
4. `advancore/agent_runner/__init__.py`
5. `advancore/agent_runner/__main__.py`
6. `tests/test_worker_fallback.py` (new)
7. `docs/architecture/AGENT_RUNNER.md`
8. `docs/decisions/ADR-022-governed-worker-fallback-boundary.md` (new)
9. `tasks/TASK-022-governed-worker-fallback-boundary.md`

Any additional path requires controller approval before modification.

## Database impact

None.

## Safety requirements

- Read and obey `AGENTS.md`.
- Stay on `agent-control-foundation`; `main` remains untouched.
- Preserve TASK-009 through TASK-021 authority and artifact semantics.
- Keep all subprocess execution argv-based with no shell interpolation.
- Default to no fallback and fail closed on unknown or ambiguous state.
- Standard-library-first; add no dependency.

## Acceptance criteria

- [ ] Codex implements the existing WorkerAdapter boundary.
- [ ] Codex argv uses bounded non-interactive workspace-write execution.
- [ ] Dangerous/bypass flags and additional writable roots are impossible.
- [ ] Approved adapter registry rejects arbitrary commands/providers.
- [ ] Fallback is explicit, optional, ordered, and limited to one adapter.
- [ ] Provider-availability failures are deterministically classified.
- [ ] Clean branch/HEAD/index/worktree/remotes are required before fallback.
- [ ] Repository mutation or ambiguous failure prevents fallback.
- [ ] Selected workers and fallback evidence are bounded and persisted.
- [ ] Orchestration resume preserves the configured fallback.
- [ ] Codex cannot create controller authority or publish.
- [ ] Existing Kimi behavior remains compatible.
- [ ] Exact nine-file implementation scope is respected.
- [ ] Full pytest suite passes.
- [ ] ADR, architecture docs, and completion report are complete.

## Test requirements

At minimum test:

1. Codex missing executable returns bounded unavailable failure.
2. Codex command is argv-only and contains required safe flags.
3. Codex command never contains dangerous bypass, danger-full-access,
   add-directory, remote/cloud, search, or arbitrary config flags.
4. Unknown adapter name is rejected.
5. Default configuration has no fallback.
6. Explicit Kimi-to-Codex fallback is accepted.
7. Duplicate primary/fallback and dry-run fallback are rejected.
8. Missing executable with unchanged repository invokes fallback once.
9. Quota/capacity/rate-limit failure with unchanged repository invokes fallback.
10. Authentication-unavailable failure with unchanged repository invokes fallback.
11. Primary repository mutation blocks fallback.
12. Primary branch/HEAD/staging/remote mutation blocks fallback.
13. Unknown failure blocks fallback.
14. Test/diff/scope failures do not trigger provider fallback.
15. Fallback result still runs the complete existing verification sequence.
16. Reports identify primary, reason, fallback, and terminal worker.
17. Artifacts exclude transcripts, credentials, environment dumps, and raw output.
18. Checkpoint persists fallback and resume cannot silently replace it.
19. Codex worker instruction prohibits approval/publication actions.
20. Existing TASK-017 through TASK-021 tests remain passing.

Run:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Constraints

- Do not implement a general-purpose command runner.
- Do not add vendor credentials or remote control.
- Do not weaken sandbox, approval, exact-scope, or controller gates.
- Do not self-approve or self-finalize TASK-022.

## Owner decisions

The owner has approved support for Codex or another explicitly approved worker
as a fail-closed fallback when Kimi is unavailable. This does not authorize
silent fallback, arbitrary commands, dangerous permission bypasses, controller
authority, `main` changes, merge, or deployment.

The DRAFT specification still requires controller/owner review and an explicit
`DRAFT -> READY` transition before implementation.

## Completion report

### Implemented

### Files changed

### Database changes

### Tests and results

### Assumptions

### Risks / unresolved issues

### Decisions required

### Recommended next step
