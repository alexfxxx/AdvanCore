# Kimi-first worker routing

> Core-readiness policy update, 29 August 2026: Kimi Swarm is now an opt-in
> worker for eligibility-gated large or genuinely parallel tasks. Routine module
> implementation should prefer Gemini, with Codex as the controller/final
> fallback. Existing Kimi-first code paths remain fail-closed compatibility
> boundaries until a separately reviewed routing change is published. See
> `docs/architecture/WORKER_EFFICIENCY_POLICY.md`.

Unattended implementation uses the fixed registered route Kimi-Swarm first,
Gemini second, and Codex last. Each provider's executable, authentication,
quota/limit, and capacity are checked by its bounded process attempt. The
auto-pipeline moves to the next worker only for an eligible classified failure
after repository integrity is proven unchanged.

Legacy Kimi usage evidence is informational only. Missing, stale, unreadable,
or 20%-plus weekly evidence, and local weekly-runtime accounting, do not gate or
shorten a Kimi launch. The provider CLI is authoritative for runtime
authentication, quota/limit, and capacity failures. AdvanCore does not infer
quota from local evidence or provider output beyond the existing bounded failure
classification.

Standing authority is consumed at actual launch. Fallback consumes a separate
approved-fallback action. Neither route receives new credentials or approval,
merge, `main`, deployment, business or compliance authority.

Each completed implementation-worker attempt may project one controller-owned
timeline event outside the repository. The load/retention/atomic-replace cycle
is serialized with an owner-only lock so concurrent completions cannot overwrite
one another. The controller validates the state path before changing permissions,
opens every owner-directory component without following symlinks, and uses
descriptor-based ownership checks and permission changes before creating the
lock. Timeline reads, temporary creation, replacement, cleanup and directory
sync all remain relative to that same verified descriptor, so an ancestor swap
cannot redirect state into another directory. Stored metadata is restricted to
registered workers and closed
sets of known terminal, failure, executable-resolution and runtime-path
classifications; arbitrary or credential-shaped strings are rejected. Malformed,
oversized, future-dated and recursively nested JSON records are discarded
fail-closed. Start and finish timestamps must be within the retention window and
cannot occur after their event timestamp. Prompts, commands, paths, output and
environment values are never stored.
Before enforcing the record cap, retained and newly arrived events are sorted
again by occurrence time with a deterministic safe-payload tie-break. A delayed
older completion therefore cannot evict newer evidence merely because it was
written later.

The registered Kimi and Kimi-Swarm adapters first use normal executable PATH
discovery. If PATH does not contain `kimi`, they may launch only the fixed
owner-home `.kimi-code/bin/kimi` path, and only when it is a non-symlink regular
executable file. Missing, non-executable, symlinked, or otherwise unsafe fixed
candidates fail closed. Explicit executable overrides remain PATH-only test
seams and do not enable caller-controlled production discovery.

## Start-of-day authentication readiness

Each new local Dashboard session runs fixed non-generative CLI checks for Kimi,
Gemini, and Codex. The checks use provider/configuration listing or login-status
commands, never a model prompt. Results are retained only in the Streamlit
session and can be rerun with **Refresh dashboard**. Raw output is discarded;
credentials, tokens, account identifiers, and provider error details are not
shown or stored.

When login is required, the Dashboard tells the owner which local CLI login
command to run. AdvanCore never accepts the password, OAuth code, or token.
Authentication failure during work is also labelled as owner-login-required;
after repository integrity passes, the workflow may continue to the next worker
in the fixed Kimi, Gemini, Codex order.

## Activated Gemini implementation worker

Gemini uses the fixed local `agy` Antigravity CLI after owner-present Google
authentication and a synthetic smoke evaluation. It is approved only for
implementation and fallback roles, not planning or review. The adapter owns its
executable name and arguments, passes the entire bounded prompt as one
`--print=<prompt>` argument, uses accept-edits mode, workspace
sandboxing, disabled slash expansion, JSON output, and a bounded timeout. It
never enables the permission-bypass flag or accepts caller-selected models,
agents, plugins, endpoints, API keys, or arbitrary command options.

The worker process receives a minimal environment. `HOME` lets the CLI use its
own existing OAuth session, but controller API keys, database URLs, GitHub
credentials, proxy variables, and loader settings are not inherited. Input
credential screening and post-worker repository verification remain mandatory.
An unavailable Google Pro balance is not treated as proof that Gemini cannot
run; actual executable, authentication, quota, and capacity failures are
classified at launch.

## Governed selection

Selection is separate from launch. For each bounded role, AdvanCore owns a
fixed preference order and accepts only explicit controller availability
evidence. Implementation prefers Kimi-Swarm, Gemini, and then Codex; planning
prefers Kimi and then Codex. Missing or stale evidence is unavailable. Registry
approval and role eligibility are checked before a name can be selected.

Selection does not consume standing authority or start a process. The selected
adapter must still pass credential screening, isolation, repository-integrity,
timeout, and launch checks. Kimi, Gemini, and Codex health is reported as
checked at launch; legacy usage evidence does not mark Kimi paused or
unavailable. Executable, authentication, quota, and capacity facts are
classified from the bounded launch result.

## Safe failover checkpoint

Provider-neutral failover state contains only bounded identifiers, the fixed
role, selected/attempted worker names, an eligible provider-failure class, and
a repository fingerprint. It stores no prompt, worker output, environment,
credential, or raw provider error.

Advancement requires the exact selected worker, an eligible classified failure,
an unchanged fingerprint, and a different available approved worker from the
fixed selection policy. The run is limited to a primary plus two fallbacks.
Checkpoint selection and persistence do not launch workers or consume standing
authority; runtime pipeline integrity checks still apply.

## Dashboard switching evidence

After an eligible failure and successful launch of the next adjacent worker,
the auto-pipeline receipt records only the previous worker, next worker, and a
safe classified reason. Executable, authentication, limit or quota, and capacity
failures are eligible only after all existing repository, index, worktree, HEAD,
branch, and remote-integrity checks pass. Unknown failures, timeout, cancellation,
unsafe or ambiguous actions, and integrity changes remain terminal and create no
switch notification.

The Dashboard reads these existing controller-owned receipts across sessions and
shows at most the five newest genuine switches from the preceding seven days.
Route previews, authentication refreshes, blocked fallbacks, and missing or
unreadable balance evidence never create a notification. The receipt contains no
raw provider output, prompt, response, transcript, credential, account identifier,
environment value, customer data, or repository path.

Provider balance or Dashboard usage evidence—whether missing, stale, above a
local percentage threshold, or unreadable—neither disables a worker nor
prevents selection, launch, or continuation. Kimi retains its macOS filesystem
sandbox, minimal environment, credential screening, and runner-owned configured
timeout. Kimi Code v0.38 may update its non-secret `workspaces.json` registry
and the single deterministic workspace-trust record for the current resolved
worktree. The workspace-trust directory is not generally writable; unrelated
trust records, credentials, OAuth state, plugins, skills and updates remain
protected, except that the Kimi CLI may refresh its own exact `oauth/kimi-code`
token and matching non-secret lock file needed for its existing authenticated
session, and synchronize only its matching `credentials/kimi-code.json` mirror.
Other files in both directories remain outside the write allowlist. No other
provider, GitHub, database, SSH or controller credential is added.
The fixed three-worker route, no-repetition and maximum-attempt
boundaries, standing and fallback authority consumption, database, production,
deployment, protected-main, and Git-integrity safeguards remain unchanged.

## Worker execution telemetry

Every bounded subprocess attempt records controller-owned start and finish
timestamps, monotonic elapsed seconds, exit code, terminal reason and a coarse
failure class. `EXECUTABLE_NOT_FOUND` means pre-flight resolution found no safe
binary. `SPAWN_ERROR` means the binary could not be loaded or returned an
executable-style 126/127 result. `RUNTIME_ERROR` means a launched process failed,
timed out or was cancelled. Provider authentication, quota and capacity routing
continues to use the existing bounded classifier and unchanged-repository gate.

The result also records the resolved executable, whether it came from normal
PATH or the governed owner-home Kimi fallback, and the named minimal runtime-path
profile. Its CLI-version field is optional and must not be populated by launching
a second provider process outside the governed isolation boundary. Raw stdout
and stderr remain available in memory long enough for immediate failure
classification, but durable audit records deliberately exclude the command,
prompt, environment, raw PATH and transcripts. This gives the owner useful
timing and failure-stage evidence without turning the audit into a credential or
business-data store. A failed or unrecognized version probe leaves the optional
field empty and does not block an otherwise valid Kimi launch. The probe has a
small output ceiling, suppresses stderr, and terminates its complete process
group on timeout, excess output, failure, or unexpected surviving descendant.
Every sandboxed Kimi or Kimi-Swarm launch validates all existing components of
every Kimi-home path exposed by its write allowlist, including proposal-only and
PATH-resolved launches. Authentication, credential-mirror, executable and trust
files are accepted only when every path component below the canonical Kimi home
is non-symlinked; malformed or recursively nested trust JSON is ignored
fail-closed.

## Automatic persistent Kimi fallback bridge

A pure controller-owned bridge connects a bounded persistent Kimi-Swarm launch
result to the existing governed failover checkpoint. Its purpose is to decide
whether Kimi-Swarm may be retired and Gemini selected next, or Gemini skipped in
favour of Codex, after an eligible provider-availability failure and only while
the repository fingerprint is unchanged.

Inputs are the existing ``FailoverCheckpoint``, a
``PersistentKimiLaunchResult``, the current repository fingerprint, and explicit
bounded ``WorkerAvailabilityEvidence`` for the approved fallback workers. The
bridge returns only whether a transition occurred, the selected next worker, the
mapped ``ProviderFailure`` class, and the resulting checkpoint.

Eligibility is strict and fail-closed:

- The checkpoint must currently select ``kimi-swarm``.
- The checkpoint role must be exactly ``IMPLEMENTATION``.
- The launch result must report ``ok=False``, ``status=WORKER_FAILED``, and
  ``reason=WORKER_FAILED``.
- The repository fingerprint must equal the checkpoint fingerprint.

Only three failure mappings are accepted:

- ``worker_failure_classification`` of ``EXECUTABLE_NOT_FOUND`` or ``SPAWN_ERROR``
  paired only with ``worker_terminal_reason=launch_failed`` maps to
  ``EXECUTABLE_UNAVAILABLE``.
- ``worker_terminal_reason`` of ``quota_or_capacity`` maps to ``QUOTA_OR_CAPACITY``.
- ``worker_terminal_reason`` of ``credential_access_required`` maps to
  ``AUTHENTICATION_UNAVAILABLE``.

Only one mapping may be present; contradictory or incomplete metadata fails
closed. Availability evidence must use exact bounded evidence and enum types,
and Gemini's state must be explicitly present before Codex can be selected.
Any other classification, terminal reason, or missing metadata fails closed with
no transition. Preflight failures, postcheck failures, successful launches,
worker exceptions, runtime errors, timeout, cancellation, authority block, and
unknown or malformed evidence are all blocked.

When eligible, the bridge delegates next-worker selection to the existing
immutable failover checkpoint using ``failed_worker="kimi-swarm"`` and the
mapped failure class. The fixed implementation route therefore selects Gemini
before Codex, and the existing no-repetition logic prevents Kimi-Swarm from
being selected again. If no approved worker is available, evidence is malformed,
or the route is exhausted, the bridge returns the original checkpoint unchanged.

The bridge itself never launches a worker, consumes standing authority, writes a
checkpoint, modifies queue state, or performs Git or publication operations. When
the bridge returns a selected next worker, the controller still launches that
worker through the existing ``AuthorizedWorkerAdapter`` and
``build_kimi_first_worker_route`` authority and integrity gates. Standing
authority is consumed at launch, not by the bridge.
