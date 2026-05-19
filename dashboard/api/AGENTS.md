# MD Dash API

## Mission Statement

Flask-based REST API that orchestrates molecular dynamics experiments across Kubernetes, manages MDRepo OAuth authentication, and coordinates with external services (MDRun, Tuner).

## Architecture & Patterns

### Design Patterns
- **Blueprint Pattern**: Routes organized into modular Flask blueprints (`experiments_bp`, `notebook_bp`, `notebook_config_bp`, `tuner_bp`, `gmx_bp`, `amber_bp`, `analysis_bp`, `files_bp`, `misc_bp`, `mdrepo_bp`)
- **Active Record Pattern**: SQLAlchemy models encapsulate business logic (e.g., `Experiment.from_pdb()`, `Experiment.publish()`)
- **Schema Pattern**: Marshmallow schemas for serialization with `@pre_dump` hooks for side effects
- **Decorator Pattern**: `@handle_exceptions(rollback=True)` for consistent error handling and transaction management
- **Singleton Pattern**: Extensions (`db`, `ma`, `migrate`) initialized as singletons in `extensions.py`
- **Factory Pattern**: `create_app()` function for Flask application initialization

### Layer Organization
```
routes/ → models/ → clients/ → external services
   ↓         ↓          ↓
schemas ← extensions ← config
```

## Core Dependencies

| Library | Purpose | Critical Path |
|---------|---------|---------------|
| `flask` | Web framework | Core request handling |
| `flask-sqlalchemy` | ORM | Database persistence |
| `flask-marshmallow` | Serialization | API response formatting |
| `flask-migrate` | Database migrations | Schema evolution |
| `kubernetes` | Kubernetes API client | Pod/job orchestration |
| `requests` | HTTP client | External API calls (MDRun, Tuner, MDRepo) |
| `cachetools` | Caching | TTLCache for status checks |

## Data Flow

```mermaid
graph TD
    A[HTTP Request] --> B[Flask Route]
    B --> C{Route Handler}
    C -->|CRUD| D[Model Methods]
    C -->|K8s Ops| E[clients/k8s.py]
    C -->|External API| F[External Clients]
    D --> G[extensions.db]
    E --> H[Kubernetes API]
    F --> I[External Services]
    G --> J[jsonify / HTTPException]
    H --> J
    I --> J
    J --> K[HTTP Response]
    
    L[MDRepo OAuth] --> M[Flask Session]
    M --> N[token_manager.py]
    N --> F
```

### Request Lifecycle
1. Request hits Flask route in `routes/`
2. Route handler calls model method or client function
3. Model/Client performs business logic (DB, K8s, external API)
4. Route returns `jsonify(data)` for success or raises `HTTPException` for errors
5. `@handle_exceptions` catches exceptions and returns `{detail: "..."}` with the correct HTTP status code

### Background Operations
- MDRepo file uploads run in daemon threads via `mdrepo.start_upload_worker()`
- No async framework used; threading for non-blocking operations

## The "Gotchas"

### Database Migrations
- **Run on startup**: `create_app()` runs `flask_migrate.upgrade()` against `dashboard/api/migrations/versions/` on every startup
- Fallback to `db.create_all()` if migration fails
- Migrations are in source control under `dashboard/api/migrations/versions/` — add a new file when adding columns
- Do NOT manually run `flask db upgrade` — the app handles it on startup

### Authentication & Sessions
- **MDRepo OAuth**: Tokens stored in Flask session, NOT database
- Use `MDRepoTokenManager(session).get_valid_token()` for authenticated requests
- Token refresh happens automatically with exponential backoff (3 retries)
- Session keys: `mdrepo_token`, `mdrepo_refresh_token`, `mdrepo_token_expires_at`

### Experiment IDs
- **5-character lowercase alphabetic strings** (e.g., `abcde`)
- Generated randomly via `get_unique_id()` - guaranteed unique within `DATA_DIR`
- Used as directory names and primary keys
- Validate with `check_experiment_id()` before use

### Kubernetes Resources
- **In-cluster config only**: `config.load_incluster_config()` called at module import
- All containers run as non-root (UID 1000) with security context
- Shared PVC mounted at `/mddash` for all pods/jobs
- Jobs have `backoffLimit: 0` (no retries on failure)
- Resource defaults: 50m CPU / 64Mi memory requests, 500m CPU / 256Mi memory limits

### File Operations
- **Git clones**: Shallow clones (`--depth 1`) without history, `.git` directory removed
- **Path validation**: Always use `check_path()` and `check_filename()` to prevent traversal
- **Excluded paths**: directory names/parts matching `.ipynb_checkpoints`, `__pycache__`, `*.edr`, `*.xtc`, `*.tpr`, `*.log`, etc.; individual files are only excluded by `EXCLUDED_FILES` patterns such as `#*#`, `*.swp`, `*.tmp`, `.nfs*`, and `.binder-env-installed`.
- **Upload filtering**: `is_excluded_path()` filters files before MDRepo upload
- **Binder support**: Cloned git repositories may contain Binder configuration files (`environment.yml`, `requirements.txt`, `postBuild`). The notebook image startup hook automatically detects and installs these environments at `/mddash/{experiment_id}/.binder-env`.

### Error Handling
- **Use `@handle_exceptions()` decorator** on JSON API route handlers; redirect-only OAuth routes in `routes/mdrepo.py` handle redirects directly.
- Set `rollback=True` for routes that modify database
- Routes return `jsonify(data)` on success; raise `HTTPException` subclasses (`BadRequest`, `NotFound`, etc.) for errors
- `@handle_exceptions` catches all exceptions, logs them, and returns `{detail: "..."}` with the correct HTTP status code

### Configuration
- All config loaded from environment variables in `config.py`
- `DATA_DIR` defaults to `/mddash` - all experiment data stored here
- `NAMESPACE` defaults to `default` but logs warning if not set
- Missing required env vars log warnings but don't crash (graceful degradation)

### Local Demo Harness
- `dashboard/api/_demo/app.py` runs the real API with test-style mocks applied before app import
- Demo seeding/mocks live in `dashboard/api/_demo/profile.py` and use real DB models/schemas/routes

### Caching
- `step_status_cache`: 100ms TTL for experiment step calculations
- `mdrepo_status_cache`: 60s TTL for MDRepo publication status
- Cache keys include experiment ID for proper invalidation

## Entry Points

| File | Purpose | Key Functions |
|------|---------|---------------|
| `app.py` | Flask application factory | `create_app()` |
| `routes/__init__.py` | Blueprint registration | Imports all route blueprints |
| `config.py` | Environment configuration | All env var loading and validation |
| `extensions.py` | Extension initialization | `db`, `ma`, `migrate` singletons |

### Route Entry Points
- `routes/experiments.py` - Experiment CRUD operations
- `routes/notebook.py` - Jupyter notebook pod management
- `routes/notebook.py` (`notebook_config_bp`) - Notebook resource option discovery
- `routes/tuner.py` - GROMACS tuner job orchestration
- `routes/gmx.py` - GROMACS simulation job management
- `routes/amber.py` - AMBER simulation job management
- `routes/analysis.py` - Analysis job management
- `routes/files.py` - File listing and download
- `routes/mdrepo.py` - MDRepo OAuth flow and callbacks
- `routes/misc.py` - Health check and metrics endpoints

### Model Entry Points
- `models/experiment.py` - Core experiment lifecycle (`from_pdb`, `from_repo`, `from_files`, `publish`, `delete`)
- `models/notebook.py` - Notebook pod lifecycle
- `models/gromacs_job.py` - GROMACS job lifecycle
- `models/amber_job.py` - AMBER job lifecycle
- `models/simulation_job.py` - Shared simulation job base model
- `models/analysis_job.py` - Analysis job lifecycle
- `models/tuner_job.py` - Tuner job lifecycle

### Client Entry Points
- `clients/k8s.py` - Kubernetes resource management (`create_notebook_pod`, `create_job`, `get_pod_status`)
- `clients/mdrepo.py` - MDRepo API client (`create_experiment`, `upload_file`, `check_experiment_status`)
- `clients/metadump.py` - MetaDump API client for extracting GROMACS TPR metadata before publishing
- `clients/mdrun.py` - MDRun API client (`create_job`, `get_job`, `delete_job`)
- `clients/tuner.py` - Tuner API client
- `clients/caddy.py` - Caddy reverse proxy configuration
