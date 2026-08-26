# AI Usage Dashboard Runbook

## Purpose

The Dashboard gives the owner one truthful view of Kimi, Codex, and Gemini
capacity evidence. It never converts chat history into a balance and never
probes a provider account from the Streamlit process.

## What each card means

- **Kimi** uses the existing controller-owned weekly percentage, reset time,
  20% automation cap, and local runtime ledger.
- **Codex** shows an exact balance only if an approved export is recorded.
  OpenAI's organization Usage API is not treated as a Codex desktop
  subscription feed.
- **Gemini** can show a measured Antigravity request token count. This is a
  historical observation, not the remaining Google Pro allowance. An exact
  percentage remains unavailable until Google exposes or the owner supplies a
  supported reading.

`Unavailable` is an expected safe result. It means AdvanCore has no current,
approved evidence; it does not mean the subscription has no capacity.

## Controller observation command

An approved local controller can record a bounded, non-secret observation:

```bash
.venv/bin/python -m advancore.services.ai_usage_dashboard_service record \
  --provider gemini \
  --observed-at 2026-08-26T13:00:00Z \
  --source antigravity-cli-json \
  --last-run-tokens 31142
```

The receipt stores only provider name, source label, observation time, optional
last-run tokens, and an optional owner-verified percentage/reset pair. It stores
no credential, account identity, prompt, response, transcript, or customer data.

## Governance boundary

Dashboard evidence is read-only and advisory. It cannot approve or activate a
worker, alter routing, purchase credits, enable billing, or weaken
`agent_runner`. Gemini remains candidate-only until a separate governed
activation decision.

