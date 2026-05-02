# GROMACS MetaDump Integration

Date: 2026-05-02

## Summary

Integrate GROMACS MetaDump API into the experiment publishing flow. Before publishing to MDRepo, extract metadata from all GROMACS TPR files via `https://gmd.ceitec.cz/api/annotate`. Pass extracted metadata into the InvenioRDM record via the existing `mdrepo.create_experiment()` call.

## Background

- `Experiment.publish()` creates MDRepo record with metadata `{"simulations": []}` (empty, never populated)
- Each GROMACS simulation has a `.tpr` file on disk at `DATA_DIR/{exp_id}/{tpr_name}`
- TPR files are excluded from MDRepo file upload but available on disk during publish
- MetaDump provides HTTP API: POST file -> get UUID, poll status, GET results, DELETE cleanup
- Experiment can have multiple GROMACS jobs -> multiple TPR files

## Design

### 1. MetaDump Client (`clients/metadump.py`)

```python
extract_metadata_bulk(tpr_paths: list[Path]) -> list[dict]
```

Flow:
1. POST each TPR file to `{METADUMP_API_URL}/api/annotate` (multipart form data). Collect `(uuid, pin)` pairs.
2. Poll loop: every 5s, check all pending UUIDs via `GET /api/annotate/{uuid}`. Move completed -> results set. Fail fast if any job returns error.
3. Timeout after 150 seconds total. If timeout, raise `InternalServerError`.
4. GET results for each completed UUID via `GET /api/annotate/{uuid}/results`.
5. DELETE each UUID with its PIN for cleanup.
6. Return list of result dicts in same order as input paths.

Single-job wrapper for testability:
```python
extract_metadata(tpr_path: Path) -> dict
```
(calls `extract_metadata_bulk` with one path, returns first result)

On any failure (upload HTTP error, timeout, API error, missing UUID) -> raise InternalServerError with message that propagates to user.

### 2. Experiment Model (`models/experiment.py`)

In `publish()` method, before creating MDRepo record:

1. Filter simulation jobs to GROMACS only: `[j for j in self.simulation_jobs if j.engine == Engine.GMX]`
2. Build TPR path list: `[DATA_DIR / self.id / j.tpr_name for j in ...]`
3. Call `metadump.extract_metadata_bulk(tpr_paths)` if list is non-empty
4. Build metadata: `{"simulations": results}` (empty list if no GROMACS jobs)
5. Pass metadata to `mdrepo.create_experiment(access_token, community, metadata)`

### 3. Configuration

```python
# dashboard/api/config.py
METADUMP_API_URL: str | None = os.environ.get("METADUMP_API_URL")
```

No default URL. If missing, env var not set -> no publish. Warning logged if absent (consistent with other optional configs).

Env var pipeline:
- `config.yaml` + `config.dev.yaml` + `config.edc.yaml`: add `metadump.url: "https://gmd.ceitec.cz"`
- `helm/charts/mddash/values.yaml.tmpl`: add `METADUMP_API_URL: value: "{{ $cfg.metadump.url }}"`
- `helm/charts/mddash/files/pre_spawn_hook.py`: add `"METADUMP_API_URL"` to env_keep list

### 4. Demo / Test Mocks

In `_demo/mocks/http.py`, add responses mocks for MetaDump endpoints:
- `POST /api/annotate` -> `{"uuid": "<uuid>", "pin": "123456", "status_url": "...", "results_url": "..."}`
- `GET /api/annotate/{uuid}` -> `{"uuid": "...", "status": "completed", "created": "...", "options": {"keep": false}}`
- `GET /api/annotate/{uuid}/results` -> minimal valid MetaDump JSON output
- `DELETE /api/annotate/{uuid}` -> `{"message": "Job <uuid> deleted"}`

Add `dashboard/api/tests/unit/test_metadump.py` testing:
- Single TPR submit + poll + result
- Multiple TPRs in bulk
- Timeout handling
- HTTP error handling
- Missing env var handling

## Error Handling

- MetaDump API down -> `InternalServerError`, publish fails before MDRepo record created
- Timeout -> `InternalServerError` with clear message
- No GROMACS jobs -> publish proceeds with empty `simulations` list
- Missing `METADUMP_API_URL` env var -> publish proceeds without MetaDump metadata (same as today)

## Files Changed

| File | Change |
|------|--------|
| `dashboard/api/clients/metadump.py` | New client file |
| `dashboard/api/models/experiment.py` | Call `metadump.extract_metadata_bulk()` in `publish()` |
| `dashboard/api/config.py` | Add `METADUMP_API_URL` |
| `dashboard/api/clients/__init__.py` | Add `metadump` export |
| `config.yaml` | Add `metadump.url` |
| `config.dev.yaml` | Add `metadump.url` |
| `config.edc.yaml` | Add `metadump.url` |
| `helm/charts/mddash/values.yaml.tmpl` | Add `METADUMP_API_URL` env var |
| `helm/charts/mddash/files/pre_spawn_hook.py` | Add env var to env_keep |
| `dashboard/api/_demo/mocks/http.py` | Add MetaDump mock endpoints |
| `dashboard/api/tests/unit/test_metadump.py` | New unit tests |

## No-Gos

- No CLI/embedded gmx binary approach (only HTTP API)
- No AMBER metadata extraction (MetaDump is GROMACS-specific)
- No schema mapping to InvenioRDM fields (raw MetaDump JSON goes into `simulations` list)
- No database migration (no new columns or tables)
