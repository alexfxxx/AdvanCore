# Gemini Candidate Setup Boundary

Gemini is registered in AdvanCore as a disabled candidate. It has no executable,
command, endpoint, credentials, production role, or routing preference. A
Gemini consumer subscription is not treated as proof of API/CLI entitlement,
billing status, usage allowance, or `agent_runner` authority.

Before any authentication work, the owner must be present to:

1. choose a supported Gemini access surface;
2. review that surface's data handling and retention terms;
3. confirm whether the subscription covers it or separate billing applies; and
4. authenticate directly without sending credentials through a worker prompt.

After authentication, separate governed work must collect bounded usage
evidence, perform a credential-safe smoke evaluation, review the result, and
obtain explicit owner activation approval. Until every gate passes, Gemini
remains non-launchable and absent from production routing.
