# GitHub pull-request verification

Every pull request runs the complete test suite in GitHub with a disposable
PostgreSQL service. The workflow has read-only repository permission and cannot
merge, push, deploy, access production, or make an owner/controller decision.

Codex desktop or another approved local client may create and monitor the PR.
GitHub remains source of truth and supplies independent CI evidence. Merge,
`main`, release and deployment remain separately manual.
