# Tuner

Tuner benchmarks GROMACS and AMBER execution configurations on a Ray cluster and exposes the results through a FastAPI service. It is built, tested, released, and deployed as part of MDDash.

## Development

Run the component checks from the repository root:

```bash
make test-tuner
make type-check-tuner
make build-tuner-api ENV=dev
```

The manual end-to-end test requires a deployed Tuner, KubeRay, cluster credentials, and available molecular-dynamics workers:

```bash
make -C tuner e2e ENV=dev
```

## Worker Image

The combined GROMACS and AMBER worker is a large, statically tagged image that includes licensed AMBER artifacts. It is deliberately excluded from root build targets and GitHub Actions.

Build and publish it only through its dedicated Makefile:

```bash
make -C tuner/worker push-amber ENV=dev PMEMD_TARBALL=pmemd26.tar.bz2
make -C tuner/worker push ENV=dev
```

After publishing a new static stack tag, update `tuner.worker.image` in each applicable `config*.yaml` file.

## Deployment

The Helm chart is `helm/charts/tuner` and is consumed as a local dependency of the MDDash umbrella chart. KubeRay is a cluster prerequisite and is not installed or removed by MDDash.

The API stores SQLite at `/data/tuner.db` on an RWO block volume. Inputs and trial outputs use the shared RWX `/tmp/tpr` volume mounted by the API and Ray pods. A NetworkPolicy limits direct Ray access to Tuner pods.

Active jobs are not recoverable across API restarts because their Ray references and cancellation state remain in process memory. Tuner also currently uses one shared service credential and does not enforce per-user job ownership; the API must remain cluster-internal until a tenant-aware authorization design replaces that boundary.
