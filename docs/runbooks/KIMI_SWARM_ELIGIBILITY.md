# Kimi Swarm Eligibility

The controller may evaluate an explicitly assigned `kimi-swarm` task only after
it already has a running queue claim, active matching scope reservation, ready
persistent worktree and exact verified scope manifest.

The running claim must still be inside the queue's two-hour freshness window,
the reservation lease must not exceed four hours, and the worktree branch must
belong to the same canonical task. Manifest proof is a structured, immutable
record bound to that task, exact path set, worktree branch, verification time
and bounded verification identifier; a loose success flag is not sufficient.

The pure gate accepts broad implementation work with at least 11 exact changed
paths, or architecture work explicitly classified by the controller. It never
infers architecture intent from task prose and cannot select or launch a
worker. Missing, expired, unsafe or mismatched evidence fails closed with a
bounded reason code.

Eligibility is not approval. Future launch integration must rerun all live
preflights, use `agent_runner`, preserve the Kimi → Gemini → Codex fallback
order, verify the exact post-run diff and retain all existing publication gates.
