# AI Worker Status Dashboard Runbook

## Purpose

The Dashboard gives the owner a simple operational view: bounded authentication
readiness for Kimi, Gemini, and Codex; the most recently selected worker when a
controller-owned receipt makes it known; and recent genuine automatic switches.
It does not display provider balances, percentages, token counts, evidence age,
or usage-availability details.

## Authentication readiness

Each Dashboard session uses fixed, non-generative local CLI status commands.
The result is presented only as authenticated, login required, or readiness not
confirmed. Raw command output, credentials, tokens, account identifiers, and
provider error details are never rendered. Refreshing the Dashboard reruns these
bounded checks but does not launch a worker or create a switch notification.

## Worker and switch status

The worker label comes only from existing local auto-pipeline receipts. When no
receipt supplies a known selection, the Dashboard says so and does not guess.
At most five genuine transitions from the preceding seven days are shown, newest
first. Each identifies the previous worker, next worker, UTC time, and one safe
reason: limit or quota, authentication, executable, or capacity.

Route previews and failed or blocked fallback decisions are not transitions.
Receipts older than seven days and malformed, unsafe, unknown, or non-adjacent
route entries are ignored. The status reader does not expose prompts, responses,
transcripts, raw errors, environment values, credentials, account identifiers,
customer data, or repository paths.

## Governance boundary

Missing, stale, malformed, unreadable, or unavailable balance and usage-display
evidence is not shown and by itself cannot block selection, launch, or
continuation. Existing runner-owned Kimi usage guardrails remain separate and
unchanged. Dashboard evidence is read-only: it cannot approve or activate a
worker, consume authority, alter routing, buy credits, enable billing, deploy,
or weaken agent-runner protections.
