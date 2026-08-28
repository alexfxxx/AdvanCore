# Kimi Swarm Eligibility

The controller may evaluate an explicitly assigned `kimi-swarm` task only after
it already has a running queue claim, active matching scope reservation, ready
persistent worktree and exact verified scope manifest.

The pure gate accepts broad implementation work with at least 11 exact changed
paths, or architecture work explicitly classified by the controller. It never
infers architecture intent from task prose and cannot select or launch a
worker. Missing, expired, unsafe or mismatched evidence fails closed with a
bounded reason code.

Eligibility is not approval. Future launch integration must rerun all live
preflights, use `agent_runner`, preserve the Kimi → Gemini → Codex fallback
order, verify the exact post-run diff and retain all existing publication gates.
