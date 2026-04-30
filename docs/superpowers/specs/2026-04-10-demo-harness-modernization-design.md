# Demo Harness Modernization Design

## Overview

Modernize the `_demo` harness to follow 2026 industry standards for UI development and integration testing, without requiring changes to production API code.

## Goals

1. **Correctness** - All external systems properly mocked with realistic behavior
2. **Industry Standards** - Use established mocking libraries and patterns
3. **Maintainability** - Single source of truth for mocks, clear separation of concerns
4. **No Production Changes** - All changes contained within `_demo/` directory

## Current State

### What's Working
- Comprehensive system coverage (K8s, Caddy, MDRun, Tuner, MDRepo)
- Deterministic seeded data with realistic scenarios
- Simulated job progression (GMX logs grow, tuner trials complete)

### Issues Identified

| Issue | Impact |
|-------|--------|
| Two mocking strategies (`patch` + module mutation) | Confusing, error-prone |
| Custom `SimpleResponse` class | Not realistic, diverges from actual `requests.Response` |
| Missing mocks for `gmx_get_trial_stdout/stderr` | 404 errors when accessing trial logs |
| No separation between mocking/seeding/state | Tangled responsibilities |
| Global mutable `demo_state` singleton | Hard to reason about, no reset capability |

## Proposed Architecture

```
_demo/
├── app.py              # Entry point - orchestrates setup
├── mocks/              # NEW: All mocking in one place
│   ├── __init__.py     # install_all_mocks() entry point
│   ├── http.py         # responses library for HTTP interception
│   ├── k8s.py          # Kubernetes client mocks (module-level)
│   └── tuner_logs.py   # Trial stdout/stderr mocks
├── state.py            # Runtime state (cleaned up interface)
├── seed.py             # Data seeding
├── files.py            # Test fixtures
└── profile.py          # Demo profile setup (slimmed down)
```

### Layer Separation

| Layer | Responsibility | File(s) |
|-------|---------------|---------|
| **Mocking** | Intercept external calls, return fake responses | `mocks/*.py` |
| **State** | Track runtime state (job progress, pod status) | `state.py` |
| **Seeding** | Create initial database records and files | `seed.py` |
| **Fixtures** | Static test data (PDB, TPR, logs) | `files.py`, `data/` |

## Technical Approach

### HTTP Mocking: `responses` Library

Use the `responses` library to intercept `requests` calls at the network level. This is the industry-standard approach for Python HTTP mocking.

**Why `responses`:**
- Realistic `requests.Response` objects
- Supports regex URL matching
- Supports dynamic responses based on request body
- Active maintenance, widely adopted
- No mutation of production modules needed

**Clients mocked via `responses`:**
- MDRun (`mdrun.py`)
- Tuner (`tuner.py`)
- MDRepo (`mdrepo.py`)
- Caddy (`caddy.py`)
- External downloads (PDB, Zenodo in `experiment.py`)

### Kubernetes Mocking: Module Mutation

The `kubernetes` library doesn't use `requests` internally, so we continue using module-level function replacement. This is the correct approach for non-HTTP clients.

**Pattern:**
```python
# mocks/k8s.py
from clients import k8s

def install_k8s_mocks() -> None:
    k8s.get_pod_status = _get_pod_status
    k8s.create_notebook_pod = _create_notebook_pod
    # ... etc
```

### Missing Functionality to Add

#### Trial Log Endpoints

Add mocks for:
- `tuner.gmx_get_trial_stdout(job_id, trial_id) -> str`
- `tuner.gmx_get_trial_stderr(job_id, trial_id) -> str`

These should return simulated GROMACS log output stored in `demo_state`.

### Response Registry Pattern

Centralize all HTTP mock registrations:

```python
# mocks/http.py
import responses
from re import compile as re_compile

class MockRegistry:
    """Central registry for all HTTP mocks."""

    def __init__(self, rsps: responses.RequestsMock):
        self._rsps = rsps
        self._installed = False

    def install(self) -> None:
        if self._installed:
            return
        self._install_mdrun()
        self._install_tuner()
        self._install_mdrepo()
        self._install_caddy()
        self._install_external()
        self._installed = True

    def _install_mdrun(self) -> None:
        @self._rsps.get(re_compile(rf"{MDRUN_API_URL}/jobs/(?P<job_id>[^/]+)"))
        def get_job(request): ...
        # ...
```

### State Management Improvements

Make `DemoState` more explicit with typed methods:

```python
# state.py
@dataclass
class DemoState:
    initialized: bool = False
    _notebook_status: dict[str, PodStatus] = field(default_factory=dict)
    _mdrun_jobs: dict[str, MdrunJobState] = field(default_factory=dict)
    _tuner_jobs: dict[str, TunerJobState] = field(default_factory=dict)
    # ...

    def get_notebook_status(self, experiment_id: str) -> PodStatus: ...
    def set_notebook_status(self, experiment_id: str, status: PodStatus) -> None: ...
    def get_mdrun_job(self, job_id: str) -> MdrunJobState | None: ...
    def advance_mdrun_job(self, job_id: str) -> None: ...
```

## Implementation Plan

### Phase 1: Structure Setup
1. Create `mocks/` directory with `__init__.py`
2. Add `responses` to requirements (dev dependency)

### Phase 2: HTTP Mocks Migration
1. Create `mocks/http.py` with `responses`-based mocks
2. Port MDRun mocks from `service_mocks.py`
3. Port Tuner mocks from `service_mocks.py`
4. Port MDRepo mocks from `service_mocks.py`
5. Port Caddy mocks from `service_mocks.py`
6. Port external download mocks (PDB, Zenodo)

### Phase 3: K8s Mocks Consolidation
1. Create `mocks/k8s.py` with existing K8s mocks
2. Remove duplicate `patch` calls from `app.py`

### Phase 4: Missing Mocks
1. Add `mocks/tuner_logs.py` for trial stdout/stderr
2. Integrate with `DemoState` for realistic output

### Phase 5: Cleanup
1. Slim down `service_mocks.py` (move all content to `mocks/`)
2. Remove `service_mocks.py` entirely
3. Update `profile.py` to use new `install_all_mocks()`
4. Clean up `app.py` to remove redundant patches
5. Update imports throughout `_demo/`

### Phase 6: State Refinement
1. Add typed state classes (`MdrunJobState`, `TunerJobState`)
2. Add convenience methods to `DemoState`
3. Ensure proper reset on re-seed

## Files Changed

| File | Change |
|------|--------|
| `requirements.txt` | Add `responses` library |
| `_demo/mocks/__init__.py` | NEW - install_all_mocks() |
| `_demo/mocks/http.py` | NEW - HTTP mocks via responses |
| `_demo/mocks/k8s.py` | NEW - K8s mocks consolidated |
| `_demo/mocks/tuner_logs.py` | NEW - Trial log mocks |
| `_demo/state.py` | Refine - typed state classes |
| `_demo/service_mocks.py` | DELETE - moved to mocks/ |
| `_demo/profile.py` | Update - use new mocks |
| `_demo/app.py` | Simplify - remove patch calls |

## Dependencies Added

```
responses>=0.25.0
```

**Why this version:** Supports `pass_through` for real requests, async support, and improved regex handling.

## Testing Strategy

1. Run demo app and verify all endpoints work
2. Test each mocked service:
   - Create/delete experiments
   - Start/stop tuner jobs
   - Run GROMACS simulations
   - Publish to MDRepo
   - Access trial logs
3. Verify no real HTTP calls made (responses assertion)

## Data Accuracy Requirements

**Critical principle:** Mocks must return realistic data matching actual API behavior.

Before implementing each mock:
1. Study production code to understand expected response fields
2. Search for official API documentation
3. Use WebSearch/WebFetch to find real response examples
4. Ask user directly if behavior is unclear

Mock data should include:
- All fields that production code reads
- Realistic values (IDs, timestamps, status strings)
- Proper error responses with correct structure
- Edge cases (empty lists, null values, error states)

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| `responses` conflicts with real requests | Use `responses.activate()` decorator only in demo context |
| Module import order matters | Install mocks before importing app (current pattern) |
| Breaking existing seeded scenarios | Keep same seed data and scenarios |
| Mock data diverges from real API | Research each API before mocking; ask user for clarification |

## Success Criteria

- [ ] All HTTP clients mocked via `responses` library
- [ ] All K8s mocks in single location
- [ ] Trial stdout/stderr accessible in UI
- [ ] No `unittest.mock.patch` in demo code
- [ ] No custom `SimpleResponse` class
- [ ] Clear separation: mocks/, state.py, seed.py
- [ ] Demo app runs without errors
- [ ] All existing seeded scenarios work unchanged