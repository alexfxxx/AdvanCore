# Worker capability registry

The registry is a code-owned description of identity and authority, not a list
of applications found on the Mac. An installed CLI, active subscription, or
visible dashboard card never grants a worker permission.

- Kimi and Kimi-Swarm are approved for their existing bounded roles and require
  fresh controller-owned usage evidence before launch.
- Codex is approved for its existing bounded planner/implementation and
  fallback roles.
- Dry-run is simulation-only and never launches a worker.
- Gemini is a setup-required candidate with no authorised role and no launch
  permission.

Callers may query deterministic immutable profiles and role eligibility. Any
unknown name or role fails closed. The registry validates itself against the
adapter allowlists so a display or routing change cannot silently create a new
worker authority path.
