# Persistent Kimi Swarm Launch

The persistent Kimi worktree is an execution location, not an authority source.
Only the controller may prepare it and call
`PersistentKimiSwarmLaunchService`. The service cannot claim or finish queue
records, acquire or release reservations, prepare manifests, choose fallbacks,
approve work or publish changes.

## Required order

1. Put the approved task on its exact `task-NNN-*` feature branch in the
   persistent registered worktree. The controller must stop if it is dirty;
   it must not reset or clean away unexplained state.
2. Claim the task through TASK-143 as `kimi-swarm` and acquire an exact,
   non-overlapping TASK-145 reservation.
3. Prepare the TASK-147 `.kimi-scope` manifest for precisely the reservation
   paths.
4. Call the launch service with the queue record, reservation and explicit
   TASK-148 work classification. The service reinspects the worktree, reads the
   manifest from disk, evaluates eligibility twice, binds the no-follow
   worktree directory identity and invokes only the existing sandboxed
   `KimiSwarmWorkerAdapter` through a descriptor-bound helper process.
5. Treat `COMPLETED` only as worker completion. The existing auto-pipeline must
   still run tests, diff checks, controller review, fallback and publication
   gates.

## Failure handling

`PREFLIGHT_FAILED` means no worker was launched. `WORKER_FAILED` may be passed
as bounded evidence to the existing Kimi → Gemini → Codex fallback controller.
`POSTCHECK_FAILED` requires controller inspection before any retry because Git
identity, staging, scope or the manifest is unsafe or ambiguous.

Each exact queue claim and reservation is consumed once through an atomic,
controller-owned receipt outside the repository. A crash leaves the receipt in
place and therefore fails closed. `LAUNCH_ALREADY_CONSUMED` means the same
evidence was replayed or another process already acquired it. Do not delete a
receipt to retry; issue a fresh governed queue claim and reservation instead.
The controller automatically compacts a receipt only after its reservation has
expired, when that evidence can no longer pass eligibility.

The result intentionally contains no prompt, command, workspace path, PATH,
stdout or stderr. Do not serialize a raw `WorkerResult`. Never grant Kimi
GitHub tokens, database URLs, SSH keys, Docker access, other provider
credentials or controller approval variables.
