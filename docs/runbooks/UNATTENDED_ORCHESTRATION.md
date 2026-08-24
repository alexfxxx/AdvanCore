# Authorized unattended orchestration

Use `orchestrate --unattended` only with `--worker kimi-swarm` and
`--fallback-worker codex`. The choice is checkpointed and cannot silently
change on resume. Each actual launch consumes exact TASK-045 routine authority;
Kimi remains subject to TASK-044 usage policy and Codex remains a one-hop
integrity-gated fallback.

Unattended mode advances only routine execution. It still pauses for task and
implementation approval, credentials, merge, `main`, deployment, destructive
actions, and business/compliance decisions.
