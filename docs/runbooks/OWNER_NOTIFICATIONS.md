# Owner notification delivery boundary

AdvanCore owns classification and produces a redacted notification feed from
its validated exception inbox. Each item contains only a stable deduplication
ID, severity, task/run labels, bounded reason and whether the owner must decide.

Codex desktop or another approved local client may poll and deliver this feed.
Delivery clients receive no command, evidence path, prompt, transcript,
credential, environment, source content or decision authority. Setting up a
scheduled Codex delivery remains an explicit Automations editor action.
