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

## Controller review and rework sequence

When a worker finishes a governed task, the controller reviews the produced
output. If the output needs another pass, the controller edits the governed task
file so that its single status line reads exactly `STATUS: REWORK` and then calls
`requeue_for_rework` on the queue:

```python
queue.requeue_for_rework("TASK-151", worker="kimi")
```

`requeue_for_rework` is fail-closed. It rejects the request unless the queued
record is currently `RUNNING` or `BLOCKED` and the governed task file's only
status is exactly `REWORK`. A `COMPLETED` record cannot be reopened; completion
is final. If the task file still says `READY`, or has any other status, the call
is rejected.

The method updates the existing record in place rather than creating a duplicate
task record. It clears the `claimed_at` and `finished_at` timestamps, returns the
record to `QUEUED`, and may assign a different approved worker name. The attempt
counter is retained across the rework cycle; it is incremented only when
`claim_next` later creates a new `RUNNING` attempt. No more than three attempts
may be claimed for one task, so a fourth `claim_next` call raises
`TaskQueueError`. This bound is enforced by the counter, which is also validated
on every queue load so that malformed or out-of-range values fail closed.

Because `STATUS: REWORK` must be set in the governed task file first, rework
never bypasses task approval and the queue itself does not approve output,
launch a worker, stage files, commit, push, publish, merge or deploy.
