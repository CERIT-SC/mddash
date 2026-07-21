# CI/CD Pipeline Redesign Spec

## Overview

Replace the current monolithic `ci-cd.yml` with separate `ci.yml` and `cd.yml` workflows. Eliminate mutable `latest` tags, replace manual `git diff` with `dorny/paths-filter`, and remove the re-tagging mechanism entirely.

## Versioning & Tags

| Environment | Branch | Tag format | Rationale |
|---|---|---|---|
| Dev | `dev` | `dev` | Mutable, acceptable for dev environment. Pull policy `Always` ensures latest. |
| Prod | `master` | `<short-sha>` (e.g. `a1b2c3d`) | Immutable, traceable, no midnight rollover bug. No `latest` anywhere. |

- Drop the `latest` tag from all registry pushes. The `build-components` re-tag block in current `ci-cd.yml` is removed.
- Makefiles compute `IMAGE_TAG` identically: `dev` for dev, `$(shell git rev-parse --short HEAD)` for prod. No date prefix.

## Pipeline Split

### `ci.yml` — Pull Requests & All Pushes

**Triggers**: `pull_request` to any branch, `push` to any branch.

**Jobs** (max parallelism):
- `lint`: ruff format + check across Python components.
- `test-dashboard-api`
- `test-dashboard-auth`
- `test-mdrun-api`
- `type-check-dashboard-api`
- `type-check-dashboard-auth`
- `type-check-mdrun-api`
- `type-check-ui`: `npm run type-check` in `dashboard/ui`

No Docker builds. No secrets for registry/kube. Fast feedback on code quality.

### `cd.yml` — Dev & Master Only

**Triggers**: `push` to `dev` or `master`.

**Jobs**:
1. `setup`: validates secrets, computes env + tag, installs `yq`.
2. `changes`: `dorny/paths-filter@v4` with filters:
   - `ui`: `dashboard/ui/**`
   - `proxy`: `dashboard/proxy/**`, `dashboard/ui/**`
   - `api`: `dashboard/api/**`
   - `auth`: `dashboard/auth/**`
   - `s3sync`: `dashboard/s3-sync/**`
   - `notebook`: `notebook/**`
   - `mdrun-api`: `mdrun-api/**`
   - `helm`: `helm/**`, `config.yaml`, `config.dev.yaml`
3. `build`: single job that builds ALL images when any component changed. Uses the same `<sha>` tag for every image.
   - Uses `docker/build-push-action` for UI/proxy/sidecars.
   - Uses `make build-*` + `make push-*` for notebook/mdrun-api (to stay DRY with local push).
4. `deploy`: depends on `build`. Runs `make -C helm deploy ENV=prod`.
5. `verify`: lightweight health check.
   - `helm status` + `kubectl get pods` for structured failure logging.
   - `curl` on `/hub/health` with 3-minute timeout (shorter than current 5 min, no pod spawn).

## Change Detection with `paths-filter`

Replace every manual `git diff --name-only` block.

```yaml
- uses: dorny/paths-filter@v4
  id: filter
  with:
    filters: |
      ui: ['dashboard/ui/**']
      proxy: ['dashboard/proxy/**', 'dashboard/ui/**']
      api: ['dashboard/api/**']
      auth: ['dashboard/auth/**']
      s3sync: ['dashboard/s3-sync/**']
      notebook: ['notebook/**']
      mdrun-api: ['mdrun-api/**']
      helm: ['helm/**', 'config.yaml', 'config.dev.yaml']
```

- `fetch-depth: 0` no longer needed for build jobs (only `setup` may keep it for `git rev-parse`).

## Build Strategy — Option A (All-or-Nothing)

One `build` job. If `changes` output shows any component or helm/config changed, build every image with the same tag.

**Pros**:
- No per-component matrix complexity.
- No risk of mixed-version images in one release.
- Eliminates the notebook-outdated bug entirely.
- Simple to implement and reason about.

**Cons**:
- Slightly longer build time when only one component changed.
- Prod deploys are infrequent; acceptable trade-off.

## Image Building Details

### Sidecars (UI, Proxy, Auth, API, S3-Sync)

Matrix build with `fail-fast: false` same as current, but triggered only if any component changed.

```yaml
build-sidecars:
  needs: [setup, changes]
  if: needs.changes.outputs.changed == 'true'
  strategy:
    fail-fast: false
    matrix:
      sidecar: [ui, proxy, auth, api, s3sync]
  steps:
    - uses: actions/checkout@v6
    - uses: docker/setup-buildx-action@v4
    - uses: docker/login-action@v4
      with: { registry: ..., username: ..., password: ... }
    - uses: docker/build-push-action@v7
      with:
        context: ...
        push: true
        tags: |
          ${{ needs.setup.outputs.registry }}/mddash/mddash-${{ matrix.sidecar }}:${{ needs.setup.outputs.tag }}
```

### Notebook & MDRun-API

Use `make` targets to stay consistent with local builds:

```yaml
build-components:
  needs: [setup, changes]
  if: needs.changes.outputs.changed == 'true'
  strategy:
    fail-fast: false
    matrix:
      component: [notebook, mdrun-api]
  steps:
    - uses: actions/checkout@v6
    - run: |
        make build-${{ matrix.component }} ENV=${{ needs.setup.outputs.env }} IMAGE_TAG=${{ needs.setup.outputs.tag }}
        make push-${{ matrix.component }} ENV=${{ needs.setup.outputs.env }} IMAGE_TAG=${{ needs.setup.outputs.tag }}
```

No `latest` tagging. No re-tagging fallback.

## Deployment Verification

Replace the current 5-minute `/hub/health` loop.

**New flow**:
1. `helm upgrade --wait --timeout 5m` (blocks until rollout complete).
2. `helm status <package> -n <ns>` for structured output.
3. `kubectl get pods -n <ns>` for visibility.
4. `curl -sf https://<host>/hub/health || exit 1` (single check, already warm from `--wait`).

Total verification time: ~1-3 minutes vs current 5+.

## Makefile Changes

Update all Makefiles to remove date-based tag computation:

```makefile
ifeq ($(ENV),dev)
  IMAGE_TAG ?= dev
else
  IMAGE_TAG ?= $(shell git rev-parse --short HEAD)
endif
```

Remove `latest` tagging logic from `build-components` in `ci-cd.yml` and from any Makefiles that push it.

## Files to Create/Modify

| File | Action |
|---|---|
| `.github/workflows/ci.yml` | Create |
| `.github/workflows/cd.yml` | Create |
| `.github/workflows/ci-cd.yml` | Delete |
| `Makefile` | Modify tag logic |
| `dashboard/Makefile` | Modify tag logic, remove `latest` push |
| `notebook/Makefile` | Modify tag logic, remove `latest` push |
| `mdrun-api/Makefile` | Modify tag logic, remove `latest` push |
| `helm/Makefile` | Verify `deploy` target works with new tags |

## Risk Mitigation

| Risk | Mitigation |
|---|---|
| First prod deploy without `latest` tag | `setup` job ensures tag is computed before any build. Helm values rendered with `IMAGE_TAG` env var. |
| Rollback still needs old tag | `helm history` already stores exact values. Rollback reuses previous Helm release values including exact tags. |
| Local `make push` on master clobbers `dev` tag | `dev` tag is only used on `dev` branch. `master` pushes use commit SHA. Separate concern. |
| Build time increase (Option A) | Prod deploys are infrequent. If builds become a bottleneck, upgrade to Option B later. |
| `paths-filter` false negative | Filters are conservative (e.g. proxy rebuilds on UI change). Better safe than stale. |

## Success Criteria

- [ ] `ci.yml` runs on every PR and push, returning in < 3 minutes.
- [ ] `cd.yml` runs only on `dev` and `master` pushes.
- [ ] Prod images tagged with commit SHA, no `latest` anywhere in registry.
- [ ] No re-tagging fallback logic remains in any workflow.
- [ ] Build skipped only when zero relevant files changed.
- [ ] Rolling prod deploy uses `--wait` and completes verification in < 5 minutes total.
