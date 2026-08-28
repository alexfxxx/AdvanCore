# Governed Task Queue

The governed task queue is a controller-owned list of task identifiers that the
owner has already approved. It provides deterministic FIFO ordering and safe,
explicit state transitions across app sessions.

An enqueue request is accepted only when its direct, non-symlink task file
exists in the repository, its title matches the requested TASK identifier, and
its single status is `READY` or `REWORK`. The same approval check is repeated
immediately before a queued record is claimed.

It is intentionally **not an executor**. Enqueueing or claiming a record does
not approve a task, launch Kimi, Gemini or Codex, run `agent_runner`, change the
database, stage files, commit, push, publish, merge or deploy. Those actions
remain behind their existing controller and owner gates.

Queue state is stored outside the worker repository as bounded JSON. The state
and lock files are owner-only, updates use atomic replacement, and malformed,
oversized, duplicate, future-dated or unsafe state fails closed. A running claim
older than two hours is marked `BLOCKED` before another queued task can be
claimed; it is never silently retried.

The queue stores only the task ID, repository-relative task specification path,
registered worker name, bounded status and timestamps. It must never contain a
prompt, task body, command, URL, credential, account detail, worker output,
business data or publication authority.
