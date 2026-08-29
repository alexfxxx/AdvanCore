# Worker Efficiency Policy

Status: approved local-development policy, 29 August 2026.

## Purpose

AI workers exist to shorten delivery. Provider troubleshooting must not become
the main development activity.

## Default use

- The controller retains planning, scope, review and publication authority.
- As a controller selection policy, Gemini is preferred for normal bounded
  implementation when it is available.
- Codex is the final implementation fallback and controller-side repair worker.
- Kimi Swarm is opt-in, not the default for routine module work.

FACT: This policy does not change the current executable routing sequence, which
remains `kimi-swarm -> gemini -> codex`. A separately governed task is required
before unattended routing can encode different provider selection behavior.

## When Kimi Swarm is suitable

Use Kimi Swarm only when the governed eligibility gate passes and the task has
at least eleven explicitly allowed files or consists of genuinely parallel
architecture work. A task is not suitable merely because it is difficult.

Do not select Kimi Swarm for one-line fixes, ordinary CRUD, Git operations,
database migrations, live service checks, credential work or a task whose
business rules are still undecided.

## Failure budget

- One bounded preflight and one governed execution attempt.
- Target maximum Kimi attempt: ten minutes unless the owner approves a longer
  task-specific limit.
- Authentication, quota, capacity or executable unavailability may move to the
  next approved provider after repository integrity is proven unchanged.
- Scope, security, artifact, Git-state or ambiguous failures stop the workflow.
- Do not perform repeated Kimi repair work during an unrelated business task.

TASK-153 remains isolated until its independent security review completes. This
policy does not weaken that gate or activate Kimi automatically.

## Evidence and review

Record worker name, bounded stage, duration and safe failure class. Never store
prompts, credentials, raw environment values or full provider transcripts.
After five eligible Kimi tasks, compare successful completion time and fallback
frequency with Gemini and Codex before changing this policy.
