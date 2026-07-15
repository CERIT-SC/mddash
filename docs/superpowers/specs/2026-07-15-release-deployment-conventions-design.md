# Release and Deployment Conventions Design

## Summary

MDDash will use `master` as its only active integration branch. Every push to
`master` will deploy the development environment, while strict SemVer tags will
create immutable production releases. The existing `dev` branch will remain as
an inactive historical branch.

The resulting release model is:

| Purpose | Git ref | Environment | Artifact tag |
|---|---|---|---|
| Pull request validation | Pull request | None | None |
| Development deployment | `master` | `dev` | `dev` |
| Production release | `vMAJOR.MINOR.PATCH` tag contained in `master` | `prod` | `MAJOR.MINOR.PATCH` |

The first release under this convention will be `v0.1.0`, producing artifacts
versioned `0.1.0`.

## Goals

- Make `master` the active integration branch and development deployment source.
- Deploy production only from explicit, immutable SemVer release tags.
- Apply one release version to every MDDash image and Helm chart.
- Keep production releases fast enough for urgent patches without a manual
  approval gate.
- Make dev and production images equivalent apart from runtime configuration.
- Make GitHub Actions workflows small, declarative, secure, cached, and
  maintainable.
- Require explicit `ENV=prod` for every local production operation.
- Change the development hostname to `dev.mddash.dyn.cloud.e-infra.cz`.

## Non-Goals

- Renaming `master` to `main`.
- Deleting the legacy `dev` branch.
- Progressive delivery, traffic splitting, or a `canary` environment.
- Independent component versioning.
- Prerelease versions such as `v1.2.3-rc.1` or build metadata.
- Deploying arbitrary unversioned working-tree application code to production.
- Introducing a tracked `VERSION` file.
- Adding a mandatory production approval step.

## Branch and Release Model

### Active Branches

`master` remains the GitHub default branch and becomes the sole active
integration branch. Pull requests target `master`; successful pushes deploy the
development environment.

The existing `dev` branch remains in the remote as a frozen historical branch.
No CI or deployment workflow responds to pushes to `dev` after cutover.

### Production Releases

A production release starts by creating a tag such as `v0.1.0` on a commit that
is contained in `master`. The release workflow must reject:

- tags that do not exactly match `v[0-9]+\.[0-9]+\.[0-9]+`;
- tags whose commit is not an ancestor of `origin/master`;
- artifact version collisions whose existing artifact points to a different
  source revision.

The leading `v` is a Git convention only. Container and Helm artifacts use the
version without it, such as `0.1.0`.

The tag push is the deliberate production-release action. Production uses a
GitHub Environment for deployment history but has no required reviewers, so an
urgent patch can proceed without a second manual gate.

After production health verification succeeds, the workflow creates a GitHub
Release for the existing tag with generated release notes. A failed deployment
does not publish a successful GitHub Release.

## Workflow Architecture

### `ci.yml`

`ci.yml` runs on all pull requests and pushes to `master`. It has no deployment
credentials and performs:

- formatting and lint checks;
- Python and TypeScript type checking;
- unit tests;
- Helm rendering, linting, and template validation;
- GitHub Actions validation with `actionlint` and `zizmor`.

The workflow also supports `workflow_call`. `release.yml` calls the same jobs so
the tagged commit passes the current quality gate before production credentials
are available.

### `deploy-dev.yml`

`deploy-dev.yml` runs from a successful `CI` `workflow_run` for a push to
`master`. It checks out that run's exact `head_sha`, then calls the reusable
deployment workflow with:

- environment `dev`;
- image tag `dev`;
- production Dockerfiles;
- development configuration;
- full-image-set build enabled.

The `workflow_run` gate avoids duplicating CI while preventing deployment of a
failed `master` push. Dev uses an environment-specific concurrency group with
superseded runs cancelled. Every run builds the complete MDDash image set, so
the newest run repairs any partial mutable-tag pushes left by a cancelled run.
This avoids the stale-component race that incremental path filtering creates
with a mutable shared tag.

Because `workflow_run` can receive elevated secrets, the deploy job must also
verify that the completed run was a successful `push`, its head branch was
`master`, and its head repository is this repository. Pull-request workflow
runs must never reach the privileged deployment job.

### `release.yml`

`release.yml` runs on tags matching `v*`, then performs these gates in order:

1. Validate strict SemVer syntax and `master` ancestry.
2. Call `ci.yml` as the release quality gate.
3. Derive the artifact version by removing the leading `v`.
4. Call the reusable deployment workflow for `prod`, building every image and
   both charts.
5. Verify production health.
6. Create the GitHub Release with generated notes.

Production uses one non-cancelling concurrency group. Releases serialize and
never interrupt an in-progress production deployment.

### `_deploy.yml`

The reusable workflow owns behavior common to dev and production:

- registry authentication;
- static image build matrices;
- Docker metadata and OCI labels;
- BuildKit cache configuration;
- image build and push;
- Helm rendering or release packaging;
- Kubernetes context and secret setup;
- atomic Helm deployment;
- health verification and failure diagnostics.

The callers provide explicit environment, image version, configuration, and
release-mode inputs. Environment behavior must not be inferred from a branch
inside the reusable workflow.

The proxy build remains dependent on the UI build because the proxy image
embeds the UI image's static assets. Other images build in parallel with
fail-fast disabled so all independent failures are reported.

The existing monolithic `cd.yml` is removed after the split workflows are in
place.

## GitHub Actions Engineering Standards

### Declarative Workflows

Workflow YAML orchestrates maintained actions and short repository commands; it
does not contain long Bash or `jq` programs. Maintained, narrowly scoped actions
handle commodity operations including checkout, language setup, dependency
caches, Docker metadata, Buildx, registry login, build/push, Kubernetes context,
and supported secret application.

MDDash-specific rules belong behind short, tested Make targets or focused
scripts. Release validation is a repository-owned unit because it combines the
project's strict version policy with Git ancestry. Tiny one-line commands remain
acceptable when wrapping them in an action would add more complexity, such as
invoking `make` or `gh release create`.

Static workflow matrices replace the current inline `jq` matrix construction.

### Supply-Chain Controls

- Pin every action to a full commit SHA and retain a nearby version comment.
- Add monthly Dependabot updates for the `github-actions` ecosystem.
- Remove downloads through mutable `releases/latest` URLs.
- Install `yq`, `gomplate`, `actionlint`, and `zizmor` from a committed Aqua
  configuration through a full-SHA-pinned `aqua-installer` action. Aqua verifies
  the configured release artifacts instead of using mutable download URLs.
- Give workflows `contents: read` by default.
- Give only the GitHub Release job `contents: write`.
- Do not expose deployment secrets to CI or image build contexts.

Repository secrets may remain during the initial cutover because environment
administration permissions are limited. The workflows still name `development`
and `production` GitHub Environments for deployment history. Secrets can move
to environment scope later without changing workflow contracts.

### Caching

- `setup-uv` caches Python dependencies using `uv.lock` inputs.
- `setup-node` and pnpm cache frontend dependencies using each pnpm lockfile.
- Each container image has a distinct registry-backed BuildKit cache reference.
- Build jobs use the registry cache as `cache-from` and update it with
  `cache-to` in `mode=max`.
- Dev and release builds share per-image caches because both use the same
  production Dockerfiles.

Registry caches are preferred over a single GitHub-hosted BuildKit cache because
the notebook image is large and durable per-image caches avoid scope collisions
and hosted-cache eviction pressure.

## Artifact Model

### Container Images

Dev images retain the mutable `dev` tag and `Always` pull policy. The term
`canary` is not used because MDDash does not perform progressive traffic rollout.

Every production image for release `v1.2.3` is tagged `1.2.3`. Builds also add
standard OCI labels for:

- version;
- source Git revision;
- source repository;
- creation time.

SemVer image tags are immutable. A retry may reuse an artifact only when its OCI
source revision matches the tagged commit; otherwise the release fails rather
than overwriting the artifact.

### Helm Charts

Both `mdrun-api` and the MDDash umbrella chart are packaged with the platform
release version. For release `v1.2.3`:

- both chart package versions are `1.2.3`;
- both `appVersion` values are `1.2.3`;
- the umbrella package depends on `mdrun-api` chart version `1.2.3`;
- production deploys the immutable umbrella chart from the OCI registry.

Release packaging stages chart metadata for the requested version without
committing a second version source to the repository. The `mdrun-api` chart is
packaged and pushed before resolving and packaging the umbrella chart.

Dev continues rendering the chart from the checked-out source with image tag
`dev`.

## Makefile Contract

All Makefiles use these rules:

- `ENV` defaults to `dev`, independent of the current Git branch.
- Only `ENV=dev` and `ENV=prod` are accepted.
- Dev defaults `IMAGE_TAG` to `dev`.
- Production build, package, and deployment internals require the release
  workflow to provide the derived immutable artifact version.
- User-facing production operational commands require only `ENV=prod`.

The supported local production operations remain:

- `make status ENV=prod`;
- `make logs ENV=prod`;
- `make history ENV=prod`;
- `make rollback ENV=prod REVISION=N`.

An arbitrary local `make all ENV=prod` is rejected with a concise message that
production application releases must use a SemVer tag. This prevents current
working-tree code from overwriting an immutable release number. Lower-level
release targets used by Actions are explicit internal contracts rather than
operator-facing commands.

Branch-based production inference and `sha-*` production image tags are removed
from the root and component Makefiles.

## Dockerfile Unification

`dashboard/api/Dockerfile.dev` and `dashboard/auth/Dockerfile.dev` are removed.
Their differences are development dependency installation and legacy Flask
debug environment variables, while their Gunicorn entrypoints already match
production. They provide little runtime debugging value and create artifact
drift.

Dev and production use the same production image artifacts. Dev debuggability
comes from runtime log levels, structured application logs, Kubernetes logs,
health endpoints, rollout diagnostics, and status commands rather than a
different dependency set or server entrypoint.

## Development Hostname Migration

`config.dev.yaml` changes the dashboard hostname from
`mddash-dev.dyn.cloud.e-infra.cz` to `dev.mddash.dyn.cloud.e-infra.cz`. The
hostname remains the single source for generated JupyterHub OAuth callbacks,
landing ingress configuration, and TLS secret naming.

Generated `helm/charts/mddash/values.yaml` is regenerated, never edited by hand.
Workflow health checks, maintained documentation, and agent instructions are
updated to use the new hostname. Historical logs are not rewritten.

Before branch cutover:

1. DNS for `dev.mddash.dyn.cloud.e-infra.cz` must resolve to the current ingress.
2. The OAuth client must allow
   `https://dev.mddash.dyn.cloud.e-infra.cz/hub/oauth_callback`.
3. The cluster issuer must be able to provision the hostname's derived TLS
   secret.

## Deployment and Failure Behavior

Deployments use `helm upgrade --install --atomic --wait` with an explicit bounded
timeout. A failed rollout restores the previous Helm release automatically.

Health verification retries `/hub/health` for a bounded period. On deployment or
health failure, the workflow emits:

- Helm release status and history;
- deployment and pod status;
- recent namespace events;
- rollout diagnostics;
- relevant container logs when available.

The workflow must preserve the original failing exit status after collecting
diagnostics.

A failed release retains its Git tag and workflow evidence but does not create a
GitHub Release. Recovery is either a safe retry that verifies existing artifact
provenance or a new patch release. Helm rollback remains available for urgent
operational recovery.

## Testing and Verification

### Static and Unit Validation

- Validate workflow syntax and semantics with `actionlint`.
- Run `zizmor` security analysis over all workflows.
- Test accepted and rejected strict SemVer tags.
- Test release rejection when the tagged commit is outside `master`.
- Test Make environment defaults and invalid environment rejection.
- Test production safeguards against unversioned local releases.
- Verify no workflow trigger remains for pushes to legacy `dev`.

### Helm Validation

- Render dev and production configurations.
- Lint and template both charts.
- Package a test release and assert matching chart versions, `appVersion`, and
  umbrella dependency version.
- Confirm generated dev ingress, OAuth callback, and TLS secret use
  `dev.mddash.dyn.cloud.e-infra.cz`.

### Repository Gates

Run the project gates in their required order:

```bash
make fix
make type-check
make test
```

Also verify all image builds select the single production Dockerfile path and
that release metadata produces the expected image tags and OCI labels.

### Post-Deployment Smoke Checks

After the first `master` deployment, verify:

- HTTPS and certificate validity on the new dev hostname;
- OAuth login and callback;
- JupyterHub health;
- user pod spawning;
- dashboard and API access.

After tagging `v0.1.0`, verify production health, deployed image versions, Helm
chart metadata, rollback history, and the generated GitHub Release.

## Cutover Sequence

1. Implement and validate the new conventions on `dev`.
2. Prepare the `development` and `production` GitHub Environments without
   required reviewers.
3. Complete DNS, OAuth callback, and TLS prerequisites for the new dev hostname.
4. Review the complete `dev` to `master` change set.
5. Merge `dev` into `master`.
6. Allow `master` CI and `deploy-dev.yml` to complete.
7. Run the dev post-deployment smoke checks.
8. Leave `dev` frozen and inactive; do not delete it.
9. Create tag `v0.1.0` on the verified `master` commit.
10. Allow the release quality gate, build, production deploy, health check, and
    GitHub Release publication to complete.
11. Verify production artifact and deployment metadata report version `0.1.0`.

## Expected File Changes

- Update `.github/workflows/ci.yml` to target `master`, support reuse, and add
  workflow validation.
- Replace `.github/workflows/cd.yml` with `deploy-dev.yml`, `release.yml`, and
  `_deploy.yml`.
- Add `.github/dependabot.yml` for monthly action updates.
- Add focused release validation and tests.
- Update the root and component Makefiles to remove branch inference and enforce
  the new environment/release contracts.
- Update Helm packaging and deployment targets for immutable OCI releases.
- Remove the API and auth `.dev` Dockerfiles.
- Update `config.dev.yaml` and regenerate Helm values.
- Update README and AGENTS instructions that describe branches, tags, workflows,
  commands, Dockerfiles, or the old development hostname.

## Success Criteria

- Pull requests and `master` pushes pass the same CI quality gates.
- A `master` push deploys all production-equivalent images as `dev` to
  `dev.mddash.dyn.cloud.e-infra.cz`.
- A push to legacy `dev` triggers neither CI nor deployment.
- Only a strict SemVer tag contained in `master` can start production deployment.
- `v0.1.0` produces immutable `0.1.0` images and matching Helm charts.
- Production deployment is atomic, serialized, health-checked, and followed by
  a generated GitHub Release.
- Operators never need to pass a version alongside `ENV=prod` for supported
  production operational commands.
- No branch-based environment inference, `sha-*` production tags, duplicated
  dev Dockerfiles, mutable tool downloads, long inline workflow scripts, or
  unpinned Actions remain.
