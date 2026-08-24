# Standing authority for unattended routine work

AdvanCore can record a short-lived owner grant for exact routine actions across
at most ten named tasks on one non-`main` branch. The grant lives in
controller-owned local state outside Git and every worker workspace.

Routine authority may cover worker execution, tests, bounded repair,
independent review, an already approved fallback, feature-branch/PR updates,
and exception reporting. It never approves a task or implementation, merges a
branch, touches `main`, deploys, changes business/compliance rules, performs a
destructive operation, or grants credentials.

Codex desktop or another approved local controller may record and consume the
grant. AdvanCore validates the exact task, branch, action, expiry and usage
budget. Missing or ambiguous authority pauses safely and appears in the normal
exception path. The worker cannot renew or broaden the grant.

When a worker requires a credential category not already approved for the
exact task, the workflow must pause for the owner. Passing the controller's
complete environment is never an acceptable substitute.
