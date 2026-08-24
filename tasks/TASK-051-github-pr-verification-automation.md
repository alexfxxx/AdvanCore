# TASK-051 — GitHub PR Verification Automation

STATUS: REVIEW

## Objective

Make GitHub independently rerun the complete project test suite for pull
requests so Codex does not become the only verification environment.

## In scope

- Add a GitHub Actions workflow for pull requests and manual dispatch.
- Use a temporary PostgreSQL service and the documented test configuration.
- Install pinned repository requirements and run the complete test suite.
- Keep the workflow verification-only with minimal read permissions.

## Out of scope

Automatic merge, push, `main` mutation, deployment, release, secrets,
production data, Bugbot replacement, or owner/controller decisions.

## Allowed changed-file scope

- `tasks/TASK-051-github-pr-verification-automation.md`
- `.github/workflows/pr-verification.yml`
- `docs/runbooks/GITHUB_PR_VERIFICATION.md`

## Owner decisions

None. Creating/updating feature PRs is routine-authorized; merging and `main`
remain manual.

## Completion report

### Implemented

- Added verification-only PR/manual GitHub CI with PostgreSQL and full pytest.
- Granted only repository-content read permission.
- Kept Codex as a replaceable local PR client rather than an AdvanCore runtime
  dependency.
- Replaced the initial fixed test password with per-run GitHub context values
  after the repository secret scanner flagged the static local fixture.

### Database changes

None. CI uses a disposable PostgreSQL service.

### Tests executed and results

- Workflow YAML parse and `git diff --check`: passed.
- Official actions are pinned to verified immutable v4/v5 tag commits.
- Repaired independent review by selecting the installed Psycopg 3 SQLAlchemy
  driver and preventing checkout from persisting GitHub's generated token for
  PR test code to read.

### Decisions required

- Independent review and PR merge remain manual.
