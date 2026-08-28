# Kimi Scope Manifest

The controller may prepare `.kimi-scope` in an already eligible dedicated Kimi
worktree. It contains only schema version, canonical TASK identifier and exact
allowed changed-file paths. It is ignored by Git and cannot approve or launch
anything.

Preparation uses an owner-only local lock and atomic replacement bound to the
verified worktree root. The controller must verify the exact manifest before
and after a future worker attempt. Missing, stale, changed, linked, non-regular,
oversized, malformed or noncanonical content fails closed.

This manifest supplements the governed task file, TASK-145 reservations,
worker sandbox and post-run diff verification. It does not replace any of them.
It stores no prompt, command, output, environment, credential, account, remote,
business data or approval/publication authority.

TASK-147 does not integrate the manifest with worker launch. Kimi trust,
authentication, CLI upgrades and actual launch remain separately governed.
