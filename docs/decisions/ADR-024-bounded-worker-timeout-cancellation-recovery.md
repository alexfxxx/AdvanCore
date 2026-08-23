# ADR-024 — Bounded Worker Timeout, Cancellation, and Recovery

**Status:** Proposed — requires independent review  
**Date:** 2026-08-23

## Context

Local provider CLIs could run indefinitely. Operator interruption could also
leave descendants running and repository mutations requiring diagnosis.

## Decision

All production worker adapters use one code-owned runner with a 1,800-second
default, a 7,200-second maximum, strict integer validation, and no executable or
signal policy supplied by users. Workers start in a new session. Timeout and
keyboard cancellation send `SIGTERM` to the complete process group, allow one
second for graceful exit, then send `SIGKILL` when required.

Terminal results discard captured output and retain only bounded reason, policy,
Git integrity, and recovery evidence. Git evidence independently covers branch,
HEAD, index, worktree, and remotes. Unchanged state yields exactly one explicit
resume/new-invocation instruction; mutation or ambiguity requires controller
review. Timeout and cancellation are ineligible for fallback, repair, or retry.
Orchestration checkpoints and auto artifacts retain the timeout and terminal
reason. Preview remains side-effect free.

## Consequences

Hung workers and descendants have bounded cleanup. Operators must explicitly
review and restart interrupted work. A worker cannot turn interruption into a
second provider attempt or publication action. The fixed timeout policy may be
revisited only through a separately reviewed change.
