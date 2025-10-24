# MDDash - Molecular Dynamics Simulation Dashboard

## Architecture Overview

Three-service Kubernetes application built on JupyterHub:
- **Dashboard** (`dashboard/`): JupyterHub + Flask API (`api/`) + React frontend (`dash/src/`)
- **mdrun-api** (`mdrun-api/`): Standalone Flask service managing GROMACS simulation jobs
- **Notebook** (`notebook/`): Per-user JupyterHub spawned containers for experiment setup

**Data flow**: User → Dashboard UI → Flask API → K8s resources (notebooks/jobs) + mdrun-api → S3/MinIO storage

## Development Workflow

All builds/deploys use `config.yaml` as single source of truth. Control environment via `ENV` variable:

```bash
make build ENV=dev          # Build all images for dev
make all ENV=prod           # Build, push, deploy to production
make status ENV=dev         # Check deployment status
```

**CI/CD**: Push to `dev` branch → dev env, `master` branch → prod env (see `.github/workflows/ci-cd.yml`)

**Helm deployment**: Uses `gomplate` to render `helm/charts/mddash/values.yaml.tmpl` from `config.yaml` before installing

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
TypeScript API layer (`dashboard/dash/src/util/api.ts`) wraps axios with consistent error handling:
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
- `helm/charts/mddash/pre_spawn_hook.py` creates per-user namespaces with RBAC on JupyterHub spawn

### Storage
- MinIO (S3-compatible) for experiment persistence
- SQLite databases for API state (`experiments.db` in dashboard, mdrun-api uses PostgreSQL in prod)
- Init containers sync S3 data to `/mddash` volume (see `get_s3_init_container()` in k8s.py)

### Authentication
OAuth2 via e-INFRA CZ (see `values.yaml.tmpl` GenericOAuthenticator config)

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
dashboard/api/          Flask API with blueprints (routes/), SQLAlchemy models, K8s clients
dashboard/dash/         React + Vite + MUI frontend, TypeScript
dashboard/auth/         JupyterHub OAuth integration
mdrun-api/              Independent Flask service for GROMACS job orchestration
helm/charts/mddash/     JupyterHub Helm chart with custom config
notebook/               Jupyter notebook image with GROMACS tools
config.yaml             Single config file for all environments
```

## Common Tasks

**Local dev**: Dashboard uses `Dockerfile.dev` with hot-reload. Frontend: `cd dashboard/dash && npm run dev`

**Check logs**: `kubectl logs -f deployment/hub -n {namespace}` or `make logs ENV=dev`

**Debug K8s resources**: JupyterHub spawner creates pods named `mddash-{username}`, mdrun-api creates jobs with generated IDs

**Template rendering**: Run `ENV=dev gomplate -d config=config.yaml -f helm/charts/mddash/values.yaml.tmpl` to test Helm values generation
