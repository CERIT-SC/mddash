# GitHub Actions Workflows

## Mission

CI/CD pipelines for MDDash: lint, test, type-check, build, deploy, and release.

## Workflow Architecture

### `ci.yml`
Runs on all PRs and `master` pushes. No deployment credentials. Performs formatting/lint checks, Python and TypeScript type checking, unit tests, Helm chart validation, and workflow validation (actionlint + zizmor). Supports `workflow_call` so `release.yml` reuses it as a release quality gate.

### `deploy-dev.yml`
Triggered by a successful `CI` `workflow_run` for a `master` push. The `verify` job checks that the triggering run was a push from this repository (fork protection). The `deploy` job calls `_deploy.yml` with dev params (`image-version: dev`, `release-mode: false`).

### `release.yml`
Triggered by `v*` tags. Validates strict SemVer (`vMAJOR.MINOR.PATCH`) and `master` ancestry. Calls `ci.yml` as a quality gate. Deploys to prod via `_deploy.yml` with `release-mode: true`. Creates a GitHub Release with generated notes on success.

### `_deploy.yml`
Reusable workflow owning: config setup, static image build matrices (fail-fast disabled), OCI labels via `docker/metadata-action`, per-image BuildKit registry cache, Helm chart packaging (prod only), atomic Helm deployment (`--atomic --wait`), health verification, and failure diagnostics.

### `codeql.yml`
CodeQL for Actions, JS/TS, Python on PRs + weekly schedule.

## Gotchas

- **`workflow_run` trigger**: zizmor flags this as `dangerous-triggers`. It's safe because the `verify` job checks `head_repository`. Suppressed in `zizmor.yml`.
- **Template injection**: inputs/secrets are passed via `env:` blocks, not `${{ }}` interpolation in `run:` scripts.
- **Actions pinned to SHAs**: all actions use full commit SHAs with version comments. Dependabot updates monthly.
- **zizmor runs with `--no-exit-codes`**: medium/warning findings (artipacked, secrets-inherit) don't fail CI. Only actionlint errors and zizmor high-severity findings fail.
- **Secrets are repo-scoped**: no GitHub Environments (repo lacks admin rights). Created in-namespace during deployment.
