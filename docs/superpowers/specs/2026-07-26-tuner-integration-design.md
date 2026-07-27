# Tuner Integration Design

## Goal

Import the former standalone tuner repository as a first-class MDDash component. MDDash will own the tuner API source, tests, dependencies, image, Helm chart, configuration, and releases. The large combined molecular-dynamics worker image remains a manually built, statically tagged artifact and must never enter the automated build or deployment pipelines.

The integrated service is named **Tuner**. Active source, configuration, artifacts, Kubernetes resources, and documentation must not use the former `gromacs-tuner` name because the service supports both GROMACS and AMBER. Engine-specific API paths and implementation names remain where they describe actual engine behavior.

## Component Layout

The imported component will use this layout:

```text
tuner/
├── AGENTS.md
├── Dockerfile
├── Makefile
├── alembic.ini
├── pyproject.toml
├── api/
├── migrations/
├── tests/
├── demo/
└── worker/
    ├── Dockerfile
    ├── Dockerfile.amber
    ├── Makefile
    └── requirements.txt

helm/charts/tuner/
├── Chart.yaml
├── values.yaml
└── templates/
```

The existing `tuner/api/` Python package remains intact. Flattening its modules into the component root or converting it to a new `src` package would add import, Alembic, Docker, and Ray runtime-environment churn without improving the service boundary.

The nested `tuner/.git` metadata must be removed so the files are tracked directly by MDDash rather than as an embedded repository or gitlink. Standalone repository configuration is either consolidated into MDDash or deleted.

## Naming

The migration applies these names consistently:

| Concern | Name |
|---|---|
| Component directory | `tuner` |
| Python project | `tuner` |
| API image | `tuner-api` |
| Worker image | `tuner-worker` |
| Helm chart and dependency | `tuner` |
| Configuration section | `tuner` |
| Kubernetes resources | `tuner-*` |
| Internal API service | `tuner-api-svc` |

The existing worker must be manually built and published to the renamed `tuner-worker` repository before a deployment switches to that reference. CI/CD will not build, copy, or retag it.

## Python Packaging And Tooling

`tuner/pyproject.toml` replaces `tuner/api/requirements.txt` and `requirements-dev.txt`. It declares Python 3.13, all API runtime dependencies, test dependencies, and `ty`. The root UV workspace includes `tuner`, and the shared `uv.lock` is regenerated.

The root Ruff configuration is authoritative. The nested tuner Ruff configuration is deleted, and imported code is normalized to repository rules. Pytest settings move into `tuner/pyproject.toml`; `tuner/pytest.ini` is removed unless a setting cannot be represented there.

The component-level `tuner/Makefile` follows the `mdrun-api` integration pattern and provides API build, push, test, and manual E2E targets. Redundant `tuner/api/Makefile` and standalone Helm Makefiles are removed. The independent `tuner/worker/Makefile` and all of its build, push, tag, AMBER-base, and cleanup commands are retained and normalized for the MDDash registry.

## Worker Boundary

The worker image contains GROMACS, licensed AMBER binaries, Ray, and supporting Python dependencies. Its large size, licensed input, and static software-stack tag make it unsuitable for routine CI/CD.

The following constraints are mandatory:

- Worker Dockerfiles, dependency input, and Make targets remain under `tuner/worker/`.
- Worker image references use a complete, static registry reference in environment configuration.
- Root aggregate `build`, `push`, and `all` targets do not invoke worker commands.
- GitHub Actions workflows contain no worker build, push, or retag step.
- The tuner Helm chart consumes the configured static worker image unchanged.
- The API image is independent and follows normal MDDash `dev` and SemVer release tags.

## Build And Release Integration

The Tuner API becomes a normal MDDash application artifact:

- Root formatting, linting, type-checking, and test targets include tuner source and tests.
- Root API build and push targets delegate to `tuner/Makefile`.
- Root aggregate build and push targets include `tuner-api` but exclude `tuner-worker`.
- CI installs locked tuner dependencies, runs pytest, and runs `ty`.
- The reusable deployment workflow builds and pushes `tuner-api` with OCI metadata and BuildKit cache, alongside other normal components.
- Development uses the mutable `dev` API tag; production uses the immutable MDDash SemVer tag.

The chart moves to `helm/charts/tuner`, beside `helm/charts/mdrun-api`. The umbrella chart uses `file://../tuner` during local development and validation. Production packaging publishes both local subcharts to the configured chart OCI namespace, rewrites both dependency repositories and versions in a temporary umbrella copy, and packages every chart with the MDDash release version.

No deployment step reaches the former standalone source or chart repository.

## Configuration

Each `config*.yaml` replaces `gromacsTuner` with `tuner`. API image configuration follows the same repository/tag model as other MDDash-built components. Worker configuration stores the complete manually managed static image reference rather than applying the platform release tag.

The values template renders the renamed chart section and distinguishes database storage from shared job storage. Resource-summary tooling reads the new configuration keys and reports resources under Tuner names.

The dashboard API changes its cluster-local URL to `http://tuner-api-svc.<namespace>.svc.cluster.local:8000/api`. Existing dashboard-to-tuner endpoint paths and authentication behavior remain unchanged.

## Runtime Storage

The standalone chart incorrectly places the SQLite WAL database and shared trial files on one RWX NFS volume. The integrated chart splits these concerns:

- `tuner-db` is an RWO block-backed PVC mounted at `/data` only by the API.
- `tuner-jobs` is an RWX filesystem PVC mounted at `/tmp/tpr` by the API, Ray head, and Ray workers.
- Database and job storage sizes and storage classes are configured independently.
- The API deployment uses the `Recreate` strategy so two API pods cannot contend for the database PVC.

Alembic migrations remain the startup authority for the tuner database. Migration failure prevents API startup rather than silently creating an unknown schema.

## Kubernetes Resources

All chart resources use the `tuner-*` naming scheme and standard chart labels. The API deployment gains Kubernetes liveness and readiness probes against `/api/health`; the Docker health check remains useful for direct container execution.

The chart does not install KubeRay. KubeRay and compatible Ray CRDs are cluster-level prerequisites managed independently from MDDash, and uninstalling MDDash must not affect the operator.

The standalone ingress template and values are removed. MDDash accesses Tuner through its cluster service, while manual E2E testing uses `kubectl port-forward`.

## API Contract Simplification

The hand-maintained OpenAPI YAML is removed. FastAPI exposes its generated schema at `/api/openapi.json`, making application routes and schemas the single source of truth. This also removes the custom schema loader, the missing-file container failure, the obsolete external hostname, and the unnecessary PyYAML dependency.

Engine-specific endpoint paths remain stable:

- `/api/tuning-jobs/gmx`
- `/api/tuning-jobs/amber`

The health endpoint remains unauthenticated for Kubernetes probes. Other existing authentication semantics remain unchanged.

## Restart Semantics

This migration fixes storage and deployment blockers but does not redesign Ray orchestration. Active thread state, cancellation events, and Ray object references remain in API process memory. An API restart can therefore mark active jobs as failed while remote work finishes or becomes orphaned.

The limitation must be documented. Durable recovery, reconciliation, or a poller-based redesign is a separate project because it changes job semantics rather than repository integration. The API deployment strategy and persistent database prevent corruption but do not claim restart-safe active jobs.

## Tests And Validation

Existing router, engine, database, utility, and Ray unit tests are retained and updated for new packaging and names. Add focused coverage for:

- Alembic startup migration against a temporary database.
- Generated OpenAPI availability at `/api/openapi.json`.
- Tuner API container configuration where practical.
- Renamed chart resources and internal service URL.
- Separate database and job PVCs, access modes, storage classes, and mounts.
- Umbrella values rendering for every supported environment config.

Cluster/GPU E2E tests remain manual through `make -C tuner e2e`. They are not part of ordinary CI because they require deployed KubeRay resources, credentials, molecular engine images, and substantial compute.

Implementation is complete only after this repository sequence passes:

```bash
make fix
make type-check
make test
make validate-charts
make lint-workflows
```

## Documentation And Cleanup

Root architecture and operational documentation will identify Tuner as source owned by this repository. A focused `tuner/AGENTS.md` will capture runtime invariants, storage rules, Ray prerequisites, migration behavior, and the manual worker policy.

Delete or consolidate these standalone artifacts:

- Nested `.git` metadata.
- Nested Ruff configuration.
- Pip requirements for the API after UV migration.
- Redundant API and Helm Makefiles.
- Static OpenAPI YAML and loader.
- Unused ingress template and values.
- Stale old-registry defaults and standalone deployment instructions.
- Duplicate ignore rules and obsolete version schemes.

Historical design documents remain unchanged because they describe the state and naming at the time they were written.

## Out Of Scope

- Building or publishing the worker image in CI/CD.
- Installing or managing the KubeRay operator.
- Durable recovery or reconciliation of active Ray jobs after API restart.
- Rewriting the dashboard tuner workflow or changing engine endpoint contracts.
- Flattening or renaming the existing `tuner/api` Python package.
