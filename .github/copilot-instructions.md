# MDDash - Molecular Dynamics Simulation Dashboard

## Architecture Overview

Three-service Kubernetes application built on JupyterHub:
- **Dashboard** (`dashboard/`): User pods with sidecar containers (proxy, auth, api, s3-sync) + stock JupyterHub singleuser
- **mdrun-api** (`mdrun-api/`): Standalone Flask service managing GROMACS simulation jobs
- **Notebook** (`notebook/`): Custom Jupyter image for experiment setup pods (spawned by dashboard API, not JupyterHub)

### Dashboard Sidecar Architecture

Each user pod runs 5 containers:
| Container | Directory | Port | Purpose |
|-----------|-----------|------|---------|
| **proxy** | `dashboard/proxy/` | 8888 | Caddy reverse proxy + React UI static files |
| **auth** | `dashboard/auth/` | 5001 | JupyterHub OAuth forward authentication |
| **api** | `dashboard/api/` | 5000 | Flask backend API |
| **s3-sync** | `dashboard/s3-sync/` | - | rclone bidirectional S3 sync daemon |
| **notebook** | (stock image) | 8080 | JupyterHub singleuser |

**Data flow**: User → Caddy proxy → Auth check → API/Notebook → K8s resources + mdrun-api → S3/MinIO storage

## Development Workflow

Configuration split by environment: `config.dev.yaml` (dev), `config.yaml` (prod). Control via `ENV` variable:

```bash
# Build all sidecar images
cd dashboard && make build ENV=dev

# Build and push all images (from root)
make push ENV=dev

# Deploy via Helm
make deploy ENV=dev
```

**CI/CD**: Push to `dev` branch → uses `config.dev.yaml`, `master` branch → uses `config.yaml` (see `.github/workflows/ci-cd.yml`)

**Helm deployment**: Uses `gomplate` to render `helm/charts/mddash/values.yaml.tmpl` from the appropriate config file before installing

## Core Patterns

### Flask API Response Pattern
All routes use standardized response handling:
```python
from api_response import ApiResponse
from decorators import handle_exceptions

@experiments_bp.route('/<id>', methods=['GET'])
@handle_exceptions()  # Use rollback=True for mutations
def get_experiment(id: str):
    experiment = Experiment.query.get_or_404(id)
    return ApiResponse.success(schema.dump(experiment))
```

### Experiment Model Pattern
Experiments use class methods for different creation flows:
- `Experiment.from_pdb(name, pdb_id)` - Download from RCSB PDB
- `Experiment.from_repo(name, zenodo_url)` - Import from Zenodo
- `Experiment.from_tpr(name, file)` - Upload TPR simulation file

Each creates a 5-character unique ID and directory at `/mddash/{experiment_id}` (see `models/experiment.py`)

### Frontend API Pattern
TypeScript API layer (`dashboard/ui/src/util/api.ts`) wraps axios with consistent error handling:
```typescript
export const get_experiment = async (id: string): Promise<ApiData<Experiment>> => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments/${id}`),
        'Failed to fetch experiment.'
    )
}
```

## Key Integration Points

### Cross-Service Communication
- Dashboard → mdrun-api: HTTP calls via K8s service DNS (`http://mdrun-api.{namespace}.svc.cluster.local/api`)
- See `dashboard/api/clients/mdrun.py` for client implementation

### Kubernetes Resource Management
- `dashboard/api/clients/k8s.py` manages pods/jobs using kubernetes-python client
- `helm/charts/mddash/pre_spawn_hook.py` creates per-user namespaces with RBAC and configures sidecar containers on JupyterHub spawn

### Storage
- MinIO (S3-compatible) for experiment persistence
- SQLite databases for API state (`experiments.db` in dashboard, mdrun-api uses PostgreSQL in prod)
- s3-sync sidecar handles bidirectional sync between S3 and `/mddash` volume

### Authentication
- OAuth2 via e-INFRA CZ (see `values.yaml.tmpl` GenericOAuthenticator config)
- Forward auth handled by `dashboard/auth/auth.py` sidecar, validates JupyterHub tokens

## Experiment Lifecycle

Experiments follow a multi-step wizard pattern tracked via `Experiment.step` property:
1. **Creation** - from PDB/Zenodo/upload
2. **Setup Notebook** - JupyterLab pod for protein preparation
3. **Tuning** (optional) - Auto-tune simulation parameters
4. **Simulation** - Run full MD simulation via mdrun-api
5. **Analysis** - View trajectories with MolStar viewer
6. **Publish** - Export to MDRepo/Zenodo

Status computed from associated notebook/job states (see `experiment._step_status()`)

## Directory Structure

```
dashboard/
  api/                 Flask API with blueprints (routes/), SQLAlchemy models, K8s clients
  ui/                  React + Vite + MUI frontend, TypeScript
  auth/                JupyterHub OAuth forward authentication service
  proxy/               Caddy reverse proxy configuration
  s3-sync/             rclone S3 sync daemon
mdrun-api/             Independent Flask service for GROMACS job orchestration
helm/charts/mddash/    JupyterHub Helm chart with custom config
helm/charts/mdrun-api/ Helm chart for mdrun-api deployment (used as sub-chart by mddash)
notebook/              Experiment setup Jupyter image with gmx wrapper (requires gmx sidecar)
config.yaml            Production configuration
config.dev.yaml        Development configuration
```

## Common Tasks

**Local dev**: API and auth use `Dockerfile.dev` with Flask debug mode when `ENV=dev`. Frontend: `cd dashboard/ui && npm run dev`

**Check logs**: Each sidecar has its own log stream:
```bash
kubectl logs -f <pod> -c proxy -n {namespace}
kubectl logs -f <pod> -c api -n {namespace}
kubectl logs -f <pod> -c auth -n {namespace}
kubectl logs -f <pod> -c s3-sync -n {namespace}
```

**Debug K8s resources**: JupyterHub spawner creates pods named `{helm.package}-{username}` (where helm.package comes from config), mdrun-api creates jobs with generated IDs

**Template rendering**: Run `ENV=dev gomplate -d config=config.dev.yaml -f helm/charts/mddash/values.yaml.tmpl` to test Helm values generation
