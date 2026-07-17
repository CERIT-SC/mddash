# GitHub Actions Workflows

## Mission

CI/CD pipelines for MDDash: lint, test, type-check, build, deploy, and release.

## Workflow Architecture

### `ci.yml`
Runs on PRs and via `workflow_call`. No deployment credentials. Performs formatting/lint checks, Python and TypeScript type checking, unit tests, Helm chart validation, and workflow validation (actionlint + zizmor). Called as a quality gate by both `cd.yml` and `release.yml`.

### `cd.yml`
Triggered on `push: master`. Calls `ci.yml` as a quality gate, then calls `_deploy.yml` to deploy all images tagged `dev` to the dev environment. Concurrency group cancels superseded runs.

### `release.yml`
Triggered by `v*` tags. Validates strict SemVer (`vMAJOR.MINOR.PATCH`) and `master` ancestry. Calls `ci.yml` as a quality gate. Deploys to prod via `_deploy.yml` with `release-mode: true`. Creates a GitHub Release with generated notes on success. Serialized (non-cancelling) concurrency.

### `_deploy.yml`
Reusable deployment workflow called by `cd.yml` and `release.yml`. Owns: config setup, static image build matrices (fail-fast disabled), OCI labels via `docker/metadata-action`, per-image BuildKit registry cache, Helm chart packaging (prod only), atomic Helm deployment, health verification, and failure diagnostics.

### `codeql.yml`
CodeQL for Actions, JS/TS, Python on PRs + weekly schedule.

## Gotchas

- **Chart OCI namespace**: container images use `cerit.io/xkrasa/<image>`; Helm charts use `cerit.io/xkrasa/charts/<chart>`. They must stay separate because image and chart tags otherwise overwrite each other.
- **`file://` dependency for mdrun-api**: `Chart.yaml` uses `file://../mdrun-api` so dev deploys resolve the sibling chart from local source instead of OCI. The `push-mddash-chart` Makefile target replaces it in a temporary chart copy with the chart OCI namespace for prod packaging.
- **Template injection**: inputs/secrets are passed via `env:` blocks, not `${{ }}` interpolation in `run:` scripts.
- **Actions pinned to SHAs**: all actions use full commit SHAs with version comments. Dependabot updates monthly.
- **zizmor runs with `--min-severity high`**: medium/warning findings don't fail CI.
- **Secrets are repo-scoped**: no GitHub Environments (repo lacks admin rights). Created in-namespace during deployment.
- **Helm v4**: `--atomic` is deprecated; use `--rollback-on-failure` on `helm upgrade` and `--wait` on `helm install`.
