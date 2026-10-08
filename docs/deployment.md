# Deployment

CI/CD deploys everything; manual deployment is a fallback. Run `./install.sh` for an interactive walkthrough of the manual steps (`--dry-run` shows the actions without applying).

## CI/CD setup

1. **Add GitHub secrets** (Settings, then Secrets):
   - `REGISTRY_USERNAME` / `REGISTRY_PASSWORD`: container registry credentials
   - `KUBECONFIG`: kubeconfig, base64 encoded with `cat ~/.kube/config | base64 -w 0`
   - `OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET`: OAuth client for authentication
   - `S3_ACCESS_KEY` / `S3_SECRET_KEY`: external S3 only; unused when `s3.seaweedfs.enabled: true`
   - `MDREPO_CLIENT_ID` / `MDREPO_CLIENT_SECRET`: MDRepo OAuth client for publishing experiments

   All secrets are automatically created in the namespace during deployment.

2. **Branch, release, and environment mapping**:

   | Purpose | Git ref | Env | Config | Namespace | Image tag | Pull policy |
   |---|---|---|---|---|---|---|
   | Dev deployment | `master` push | `dev` | `config.dev.yaml` | `mddash-dev` | `dev` | `Always` |
   | Prod release | `vMAJOR.MINOR.PATCH` tag | `prod` | `config.yaml` | `md-dashboard-ns` | `MAJOR.MINOR.PATCH` (immutable) | `IfNotPresent` |

   - Pull requests run CI only, with no deployment.
   - Push to `master`. CD calls CI as a quality gate, then deploys all images tagged `dev`.
   - Push a SemVer tag. Release validates SemVer, calls CI, deploys immutable images and Helm charts to prod, then creates a GitHub Release.
   - Run `make release VERSION=X.Y.Z` from a clean, up-to-date `master` checkout to create and push the release tag.
   - Production operational commands (`status`, `logs`, `history`, `rollback`) use `ENV=prod` without needing a version.

Every `master` push rebuilds the complete image set as `dev`, repairing any partial pushes from cancelled runs. Production releases require a strict SemVer tag (`v0.1.0`, `v1.2.3`) whose commit is an ancestor of `master`. SemVer tags are immutable. A retry reuses an artifact only when its OCI source revision matches the tagged commit. Services can override pull policy in configuration. The Tuner API follows platform release tags; its large worker image uses a separately managed static stack tag.

## Harbor retention policy

Configure in Harbor UI (Project → Policy → Tag Retention):

1. **Dev tags**: repository `**`, tag `dev` → retain always
2. **Prod tags**: repository `**`, tag matching `[0-9]+\.[0-9]+\.[0-9]+` → retain always

Prod SemVer tags must be retained indefinitely: `make rollback ENV=prod REVISION=N` restores a Helm release revision whose values reference a specific image tag, so evicting a live tag breaks rollback. A count-based rule on push time can evict the currently-running tag during fast hotfix cycles, since push order diverges from deploy order. Release cadence bounds the count naturally at this project's scale.

## Rollback data compatibility

Image tags are not the only rollback hazard: enum additions are forward-safe but not rollback-safe. The release that adds simulation **stop** (`JobStatus.STOPPED` on `simulation_jobs.last_known_status` and `mdrun_jobs.last_status`) writes status strings a pre-STOPPED binary cannot decode (SQLAlchemy raises `LookupError` when loading such rows, so reads fail with 500). Before rolling back across that release boundary, normalize the data in both databases (dashboard SQLite in the user pod at `/mddash/experiments.db`, MDRun SQLite at `/data/mdrun.db`):

```sql
UPDATE simulation_jobs SET last_known_status = 'ERROR' WHERE last_known_status = 'STOPPED';
UPDATE mdrun_jobs SET last_status = 'FINISHED' WHERE last_status = 'STOPPED';
```

## Manual deployment

Bypasses CI/CD. The remaining sections document the same steps `./install.sh` performs.

### 1. Prerequisites

All preinstalled in the dev container: `docker`, `kubectl`, `helm`, `yq`, `gomplate`, `uv`, `pnpm`, `make`.

### 2. Environment setup

Choose your config and env:

```bash
export ENV=dev  # or prod
export CONFIG=config.dev.yaml

export NAMESPACE=$(yq '.namespace' "${CONFIG}")
export PACKAGE=$(yq '.helm.package' "${CONFIG}")
```

### 3. Bootstrap Kubernetes resources

Create the target namespace:

```bash
kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1 || kubectl create namespace "${NAMESPACE}"
```

> [!CAUTION]
> If you are using Rancher, restrict the Resource Quota of the hub namespace so user namespaces have room. When `rancherProjectId` is set in the config, `./install.sh` does this automatically via namespace annotations; otherwise set it manually in the Rancher UI. See `docs/resource-management.md` for sizing guidance.

Set up the hub service account permissions:

> [!CAUTION]
> The hub service account gets its permissions from a Rancher role template. A Rancher admin must do this once (see `helm/rbac/roletemplate.yaml`):

1. Create the role template from `helm/rbac/roletemplate.yaml` on the management cluster (Rancher UI: Global → Security → Role Templates).
2. Bind it in the project to the group `system:serviceaccounts:<NAMESPACE>` (project members, custom principal with that exact name).

Rancher replicates the binding into every project namespace, including user namespaces created at spawn time. `./install.sh` checks for the binding and, missing, creates the template and binding through the Rancher API when the kubeconfig is Rancher-backed; otherwise it prints the manifest for an admin.

Create the secrets, replacing placeholders with actual values:

```bash
# OAuth Credentials
kubectl create secret generic oidc-credentials \
  --from-literal=client_id="YOUR_CLIENT_ID" \
  --from-literal=client_secret="YOUR_CLIENT_SECRET" \
  -n ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# S3 Credentials (external S3 only; the deployment generates it under
# s3.seaweedfs.enabled and it must stay stable)
kubectl create secret generic ${PACKAGE}-s3-creds \
  --from-literal=S3_ACCESS_KEY="YOUR_S3_ACCESS_KEY" \
  --from-literal=S3_SECRET_KEY="YOUR_S3_SECRET_KEY" \
  -n ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# MDRepo OAuth Credentials (for publishing experiments to MDRepo)
kubectl create secret generic ${PACKAGE}-mdrepo-credentials \
  --from-literal=client_id="YOUR_MDREPO_CLIENT_ID" \
  --from-literal=client_secret="YOUR_MDREPO_CLIENT_SECRET" \
  -n ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# Tuner Credentials (static user, random password, created once)
kubectl get secret tuner-auth -n ${NAMESPACE} >/dev/null 2>&1 || \
  kubectl create secret generic tuner-auth \
  --from-literal=user="tuner" \
  --from-literal=password="$(openssl rand -base64 32)" \
  -n ${NAMESPACE}
```

### 4. Build and deploy

```bash
# 1. Authenticate to the container and Helm OCI registry.
# Use the registry host from the selected config, for example cerit.io.
docker login <registry-host>
helm registry login <registry-host>

# 2. Build and push all docker images
make push ENV=${ENV}

# 3. Package and push local subcharts when they changed.
make push-mdrun-api-chart ENV=${ENV}
make push-tuner-chart ENV=${ENV}

# 4. Update Helm dependencies when charts or config changed
make -C helm update ENV=${ENV}

# 5. Deploy to Kubernetes
# For first-time installation:
make -C helm install ENV=${ENV}

# For updates:
make deploy ENV=${ENV}
```
