# Worker Scope Reservations

The controller may reserve the exact changed-file scope of an already governed
task before assigning separate work to Kimi, Gemini or Codex. An active exact or
ancestor/descendant overlap fails closed, including when two controller
processes race for the same scope.

This is a metadata safety service, not an authority boundary. A reservation does
not approve a task, launch a worker, run `agent_runner`, grant access, stage or
commit files, push, publish, merge, deploy, or change a database. The existing
controller and owner gates remain mandatory.

State is bounded and stored outside the worker repository. The directory, state
file and no-follow lock are owner-only, writes use atomic replacement, and
malformed, future-dated, oversized or unsafe state fails closed. Active
reservations expire after four hours and are marked released; they never cause
automatic execution or retry. Released evidence is retained for seven days.

Only canonical task identifiers, registered worker names, safe exact
repository-relative paths and timestamps are stored. Prompts, commands, output,
environment contents, credentials, account identifiers and business data are
prohibited.
