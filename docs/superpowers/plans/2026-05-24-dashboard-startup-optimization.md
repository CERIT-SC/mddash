# Dashboard Startup Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce dashboard API/auth first-health latency and suppress noisy successful health probe logs without weakening startup safety or observability.

**Architecture:** Keep the existing sidecar architecture. Add targeted startup timing, remove duplicate API app construction, skip Alembic upgrades only when the DB is already at head, lazy-load Kubernetes clients, delay storage scanning, make proxy waits use real health endpoints, and filter successful `mdrun-api` health access logs at the server layer.

**Tech Stack:** Python 3.12, Flask, Flask-SQLAlchemy, Flask-Migrate/Alembic, Gunicorn, uWSGI, Kubernetes Python client, Kubernetes sidecar specs in JupyterHub `pre_spawn_hook.py`, pytest, Helm/gomplate-rendered values.

---

## File Structure

| File | Responsibility |
|---|---|
| `dashboard/api/app.py` | Dashboard API factory, startup timing, migration gate, single app creation path. |
| `dashboard/api/clients/k8s.py` | Lazy cached Kubernetes API client creation for dashboard API operations. |
| `dashboard/api/routes/misc.py` | Health and metrics routes; avoid importing Kubernetes client on health-only path. |
| `dashboard/api/utils.py` | Storage-size monitor scheduling with initial delay support. |
| `dashboard/api/tests/unit/test_app_startup.py` | API startup, migration gate, and no-import-side-effect tests. |
| `dashboard/api/tests/unit/test_k8s_client.py` | Lazy Kubernetes client initialization tests. |
| `dashboard/api/tests/unit/test_utils.py` | Storage monitor delayed-start tests. |
| `dashboard/auth/auth.py` | Lightweight auth startup and first-health timing logs. |
| `dashboard/auth/tests/test_auth.py` | Auth health behavior remains covered. |
| `helm/charts/mddash/files/pre_spawn_hook.py` | Proxy sidecar startup wait command and health endpoint URLs. |
| `helm/charts/mddash/tests/test_pre_spawn_hook.py` | Proxy wait command unit tests. |
| `mdrun-api/Dockerfile` | uWSGI access-log filtering for successful `/api/health` probes. |
| `mdrun-api/tests/test_container_config.py` | Static verification of uWSGI health log filtering config. |
| `dashboard/api/AGENTS.md` | Update K8s startup gotcha after lazy loading. |
| `helm/charts/mddash/AGENTS.md` | Document proxy sidecar health wait behavior. |
| `mdrun-api/AGENTS.md` | Document successful health access-log suppression policy. |

## Task 1: Dashboard API Startup Timing, Migration Gate, And Single App Factory

**Files:**
- Modify: `dashboard/api/app.py`
- Create: `dashboard/api/tests/unit/test_app_startup.py`

- [ ] **Step 1: Write failing startup and migration tests**

Create `dashboard/api/tests/unit/test_app_startup.py` with:

```python
"""Tests for dashboard API startup behavior."""

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

from flask import Flask


def _fresh_import_app(tmp_path: Path, monkeypatch, mocker) -> ModuleType:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JUPYTERHUB_USER", "testuser")
    monkeypatch.setenv("JUPYTERHUB_SERVICE_PREFIX", "/user/testuser")
    monkeypatch.setenv("POD_NAMESPACE", "test-namespace")
    monkeypatch.setenv("HUB_NAMESPACE", "hub-namespace")
    monkeypatch.setenv("PVC_NAME", "test-pvc")
    monkeypatch.setenv("PVC_STORAGE_SIZE", "1Gi")
    monkeypatch.setenv("TUNER_USER", "tuner")
    monkeypatch.setenv("TUNER_PASSWORD", "secret")

    sys.modules.pop("app", None)
    mocker.patch("kubernetes.config.load_incluster_config")
    mocker.patch("kubernetes.client.CoreV1Api")
    mocker.patch("kubernetes.client.BatchV1Api")
    return importlib.import_module("app")


def test_importing_app_module_does_not_run_migrations(tmp_path: Path, monkeypatch, mocker) -> None:
    """Gunicorn factory imports should not construct the Flask app eagerly."""
    upgrade = mocker.patch("flask_migrate.upgrade")

    app_module = _fresh_import_app(tmp_path, monkeypatch, mocker)

    assert hasattr(app_module, "create_app")
    assert not hasattr(app_module, "app")
    upgrade.assert_not_called()


def test_run_migrations_skips_upgrade_when_database_is_at_head(app: Flask, mocker) -> None:
    """Already-current databases should avoid full Alembic upgrade machinery."""
    import app as app_module

    migration_context = MagicMock()
    migration_context.get_current_revision.return_value = "006"
    script = MagicMock()
    script.get_current_head.return_value = "006"

    mocker.patch("app.MigrationContext.configure", return_value=migration_context)
    mocker.patch("app.ScriptDirectory", return_value=script)
    upgrade = mocker.patch("app.upgrade")
    stamp = mocker.patch("app.stamp")
    inspect_db = mocker.patch("app.sa_inspect")

    with app.app_context():
        app_module._run_migrations()

    upgrade.assert_not_called()
    stamp.assert_not_called()
    inspect_db.assert_not_called()


def test_run_migrations_upgrades_when_database_is_behind_head(app: Flask, mocker) -> None:
    """Behind-head databases must still be upgraded before serving requests."""
    import app as app_module

    migration_context = MagicMock()
    migration_context.get_current_revision.return_value = "005"
    script = MagicMock()
    script.get_current_head.return_value = "006"
    script.get_revision.return_value = MagicMock()

    mocker.patch("app.MigrationContext.configure", return_value=migration_context)
    mocker.patch("app.ScriptDirectory", return_value=script)
    upgrade = mocker.patch("app.upgrade")
    stamp = mocker.patch("app.stamp")

    with app.app_context():
        app_module._run_migrations()

    stamp.assert_not_called()
    upgrade.assert_called_once_with(directory=str(app_module.MIGRATIONS_DIR))


def test_run_migrations_stamps_unversioned_database_with_tables(app: Flask, mocker) -> None:
    """Legacy unversioned DBs with existing tables keep baseline stamping behavior."""
    import app as app_module

    migration_context = MagicMock()
    migration_context.get_current_revision.return_value = None
    script = MagicMock()
    script.get_current_head.return_value = "006"
    inspector = MagicMock()
    inspector.get_table_names.return_value = ["experiments"]

    mocker.patch("app.MigrationContext.configure", return_value=migration_context)
    mocker.patch("app.ScriptDirectory", return_value=script)
    mocker.patch("app.sa_inspect", return_value=inspector)
    stamp = mocker.patch("app.stamp")
    upgrade = mocker.patch("app.upgrade")

    with app.app_context():
        app_module._run_migrations()

    stamp.assert_called_once_with(directory=str(app_module.MIGRATIONS_DIR), revision="001", purge=True)
    upgrade.assert_called_once_with(directory=str(app_module.MIGRATIONS_DIR))
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run --package dashboard-api pytest dashboard/api/tests/unit/test_app_startup.py -v
```

Expected: FAIL because `app.py` still exposes module-level `app`, has no `_run_migrations()`, and always calls `upgrade()`.

- [ ] **Step 3: Refactor `dashboard/api/app.py` startup**

Replace the contents of `dashboard/api/app.py` with this structure, preserving existing imports/routes and adding only focused startup helpers:

```python
import logging
import os
import time
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from config import DATA_DIR, LOG_FORMAT, LOG_LEVEL
from extensions import db, ma, migrate
from flask import Flask
from flask_migrate import stamp, upgrade
from logging_utils import configure_logging, enable_loggers
from routes import (
    amber_bp,
    analysis_bp,
    experiments_bp,
    files_bp,
    gmx_bp,
    mdrepo_bp,
    misc_bp,
    notebook_bp,
    notebook_config_bp,
    tuner_bp,
)
from sqlalchemy import inspect as sa_inspect
from utils import start_du_monitor

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
DU_MONITOR_START_DELAY_SECONDS = 10.0


def _log_duration(phase: str, start: float) -> None:
    """Log startup phase duration without making startup depend on instrumentation."""
    try:
        logger.info("startup phase %s completed in %.3fs", phase, time.perf_counter() - start)
    except Exception:
        pass


def _run_migrations() -> None:
    """Apply required DB migrations, skipping Alembic upgrade when already at head."""
    start = time.perf_counter()
    logger.info("Checking database migrations...")

    script = ScriptDirectory(str(MIGRATIONS_DIR))
    head_rev = script.get_current_head()

    with db.engine.connect() as conn:
        current_rev = MigrationContext.configure(conn).get_current_revision()

    if current_rev is None:
        if sa_inspect(db.engine).get_table_names():
            logger.info("Unversioned DB with tables; stamping to migration baseline...")
            stamp(directory=str(MIGRATIONS_DIR), revision="001", purge=True)
            current_rev = "001"
    else:
        try:
            script.get_revision(current_rev)
        except CommandError:
            logger.info("Unknown DB revision; restamping to migration baseline...")
            stamp(directory=str(MIGRATIONS_DIR), revision="001", purge=True)
            current_rev = "001"

    _log_duration("db-revision-check", start)

    if current_rev == head_rev:
        logger.info("Database is at migration head %s; skipping upgrade", head_rev)
        return

    start = time.perf_counter()
    logger.info("Running database migrations...")
    upgrade(directory=str(MIGRATIONS_DIR))
    _log_duration("migration-upgrade", start)


def _register_blueprints(app: Flask) -> None:
    app.register_blueprint(amber_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(experiments_bp)
    app.register_blueprint(notebook_bp)
    app.register_blueprint(notebook_config_bp)
    app.register_blueprint(tuner_bp)
    app.register_blueprint(gmx_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(misc_bp)
    app.register_blueprint(mdrepo_bp)


def create_app() -> Flask:
    """Create and configure the Flask application."""
    startup_start = time.perf_counter()
    app = Flask(__name__)

    db_path = DATA_DIR / "experiments.db"
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.environ.get("MDREPO_CLIENT_SECRET", "")
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    db.init_app(app)
    ma.init_app(app)
    migrate.init_app(app, db, directory=str(MIGRATIONS_DIR))

    _register_blueprints(app)
    _log_duration("route-registration", startup_start)

    with app.app_context():
        try:
            _run_migrations()
        except (Exception, SystemExit) as e:
            logger.warning("Migration upgrade failed: %s, falling back to create_all()", e)
            db.create_all()

    configure_logging(LOG_FORMAT, LOG_LEVEL)
    enable_loggers()

    start_du_monitor(DATA_DIR, initial_delay=DU_MONITOR_START_DELAY_SECONDS)
    _log_duration("app-factory", startup_start)

    return app


if __name__ == "__main__":
    logger.info("Starting Flask development server...")
    create_app().run(debug=True, host="0.0.0.0", port=5000)
```

- [ ] **Step 4: Run focused API startup tests**

Run:

```bash
uv run --package dashboard-api pytest dashboard/api/tests/unit/test_app_startup.py -v
```

Expected: PASS.

- [ ] **Step 5: Run API health integration test**

Run:

```bash
uv run --package dashboard-api pytest dashboard/api/tests/integration/test_health.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

Run:

```bash
git add dashboard/api/app.py dashboard/api/tests/unit/test_app_startup.py
git commit -m "perf(dashboard-api): Trim startup migration path" \
  -m "Avoid duplicate app construction and skip Alembic upgrade when the dashboard DB is already at head. Add startup timing logs around the critical first-health path."
```

## Task 2: Lazy-Load Dashboard API Kubernetes Clients

**Files:**
- Modify: `dashboard/api/clients/k8s.py`
- Modify: `dashboard/api/routes/misc.py`
- Create: `dashboard/api/tests/unit/test_k8s_client.py`

- [ ] **Step 1: Write failing lazy-load tests**

Create `dashboard/api/tests/unit/test_k8s_client.py` with:

```python
"""Tests for lazy dashboard Kubernetes client initialization."""

import importlib
import sys
from pathlib import Path


def test_importing_k8s_client_does_not_load_incluster_config(tmp_path: Path, monkeypatch, mocker) -> None:
    """Importing the client module should not touch Kubernetes configuration."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("POD_NAMESPACE", "test-namespace")
    monkeypatch.setenv("PVC_NAME", "test-pvc")
    monkeypatch.setenv("PVC_STORAGE_SIZE", "1Gi")
    monkeypatch.setenv("TUNER_USER", "tuner")
    monkeypatch.setenv("TUNER_PASSWORD", "secret")

    sys.modules.pop("clients.k8s", None)
    load_config = mocker.patch("kubernetes.config.load_incluster_config")
    core_api = mocker.patch("kubernetes.client.CoreV1Api")
    batch_api = mocker.patch("kubernetes.client.BatchV1Api")

    importlib.import_module("clients.k8s")

    load_config.assert_not_called()
    core_api.assert_not_called()
    batch_api.assert_not_called()


def test_get_core_v1_loads_config_once(mocker) -> None:
    """First Kubernetes use should initialize config once and cache clients."""
    import clients.k8s as k8s

    k8s.reset_k8s_clients_for_tests()
    load_config = mocker.patch("clients.k8s.config.load_incluster_config")
    core_api = mocker.patch("clients.k8s.CoreV1Api")

    first = k8s.get_core_v1()
    second = k8s.get_core_v1()

    assert first is second
    load_config.assert_called_once_with()
    core_api.assert_called_once_with()


def test_get_batch_v1_loads_config_once(mocker) -> None:
    """Batch client creation should share the same in-cluster config load."""
    import clients.k8s as k8s

    k8s.reset_k8s_clients_for_tests()
    load_config = mocker.patch("clients.k8s.config.load_incluster_config")
    batch_api = mocker.patch("clients.k8s.BatchV1Api")

    first = k8s.get_batch_v1()
    second = k8s.get_batch_v1()

    assert first is second
    load_config.assert_called_once_with()
    batch_api.assert_called_once_with()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run --package dashboard-api pytest dashboard/api/tests/unit/test_k8s_client.py -v
```

Expected: FAIL because `clients.k8s` loads config at import time and has no lazy helpers.

- [ ] **Step 3: Add lazy client helpers**

In `dashboard/api/clients/k8s.py`, replace lines 41-43 with:

```python
_k8s_lock = threading.Lock()
_k8s_config_loaded = False
_core_v1: CoreV1Api | None = None
_batch_v1: BatchV1Api | None = None


def _load_k8s_config_once() -> None:
    global _k8s_config_loaded  # noqa: PLW0603
    if _k8s_config_loaded:
        return
    with _k8s_lock:
        if _k8s_config_loaded:
            return
        config.load_incluster_config()
        _k8s_config_loaded = True


def get_core_v1() -> CoreV1Api:
    """Return a cached CoreV1Api client, loading in-cluster config on first use."""
    global _core_v1  # noqa: PLW0603
    if _core_v1 is None:
        _load_k8s_config_once()
        _core_v1 = CoreV1Api()
    return _core_v1


def get_batch_v1() -> BatchV1Api:
    """Return a cached BatchV1Api client, loading in-cluster config on first use."""
    global _batch_v1  # noqa: PLW0603
    if _batch_v1 is None:
        _load_k8s_config_once()
        _batch_v1 = BatchV1Api()
    return _batch_v1


def reset_k8s_clients_for_tests() -> None:
    """Reset cached Kubernetes clients for isolated unit tests."""
    global _batch_v1, _core_v1, _k8s_config_loaded  # noqa: PLW0603
    _core_v1 = None
    _batch_v1 = None
    _k8s_config_loaded = False
```

- [ ] **Step 4: Replace global client usage with local lazy clients**

In `dashboard/api/clients/k8s.py`, replace every method body reference to the old globals with local client variables. Use this exact pattern:

```python
core_v1 = get_core_v1()
core_v1.create_namespaced_pod(namespace=NAMESPACE, body=pod_manifest)
```

```python
batch_v1 = get_batch_v1()
batch_v1.create_namespaced_job(namespace=NAMESPACE, body=job_manifest)
```

Apply the same replacement for every current `core_v1.*` and `batch_v1.*` call site in `clients/k8s.py`.

- [ ] **Step 5: Avoid importing Kubernetes on health-only path**

Modify `dashboard/api/routes/misc.py` so the module does not import `clients.k8s` at import time. Change:

```python
from clients import k8s
```

to no import, and update `get_metrics()` to import only when needed:

```python
def get_metrics() -> Response:
    """Get resource usage metrics for the current user."""
    from clients import k8s

    if "pod_resources" in metrics_cache:
        pod_requests = metrics_cache["pod_resources"]
    else:
        pod_requests = k8s.get_pod_resource_requests()
        metrics_cache["pod_resources"] = pod_requests

    requests: dict[str, int | None] = {**pod_requests, "storage": get_du_size(DATA_DIR)}

    limits = {
        "cpu": k8s.parse_cpu(CPU_REQUEST_QUOTA),
        "memory": k8s.parse_memory(MEMORY_REQUEST_QUOTA),
        "storage": k8s.parse_memory(PVC_SIZE),
    }

    return jsonify({"requests": requests, "limits": limits})
```

- [ ] **Step 6: Run lazy client and health tests**

Run:

```bash
uv run --package dashboard-api pytest dashboard/api/tests/unit/test_k8s_client.py dashboard/api/tests/integration/test_health.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

Run:

```bash
git add dashboard/api/clients/k8s.py dashboard/api/routes/misc.py dashboard/api/tests/unit/test_k8s_client.py
git commit -m "perf(dashboard-api): Lazy-load Kubernetes clients" \
  -m "Keep dashboard health import independent of in-cluster Kubernetes setup. Initialize cached Kubernetes clients only when endpoints need them."
```

## Task 3: Delay Dashboard Storage-Size Monitor Startup

**Files:**
- Modify: `dashboard/api/utils.py`
- Modify: `dashboard/api/tests/unit/test_utils.py`

- [ ] **Step 1: Write failing delayed monitor tests**

Append this test class to `dashboard/api/tests/unit/test_utils.py`:

```python
class TestDuMonitor:
    """Tests for storage-size monitor startup."""

    def test_start_du_monitor_passes_initial_delay_to_thread(self, tmp_path: Path, mocker) -> None:
        """The first du scan should be delayable to avoid first-health IO contention."""
        thread_cls = mocker.patch("utils.threading.Thread")
        mocker.patch("utils.threading.enumerate", return_value=[])

        from utils import start_du_monitor

        start_du_monitor(tmp_path, initial_delay=7.5)

        thread_cls.assert_called_once()
        assert thread_cls.call_args.kwargs["args"] == (tmp_path, 7.5)
        thread_cls.return_value.start.assert_called_once_with()

    def test_du_loop_sleeps_before_first_measurement_when_initial_delay_set(self, tmp_path: Path, mocker) -> None:
        """A configured initial delay should happen before subprocess du runs."""
        sleep = mocker.patch("utils.time.sleep", side_effect=RuntimeError("stop"))
        run = mocker.patch("utils.subprocess.run")

        from utils import _du_loop  # noqa: PLC2701

        try:
            _du_loop(tmp_path, initial_delay=3.0)
        except RuntimeError:
            pass

        sleep.assert_called_once_with(3.0)
        run.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run --package dashboard-api pytest dashboard/api/tests/unit/test_utils.py::TestDuMonitor -v
```

Expected: FAIL because `_du_loop()` and `start_du_monitor()` do not accept `initial_delay`.

- [ ] **Step 3: Add initial delay support**

In `dashboard/api/utils.py`, change `_du_loop()` and `start_du_monitor()` to:

```python
def _du_loop(data_dir: Path, initial_delay: float = 0.0) -> None:
    """Background thread body: measure data_dir size every DU_INTERVAL seconds."""
    if initial_delay > 0:
        time.sleep(initial_delay)

    size_file = data_dir / DU_SIZE_FILENAME
    while True:
        try:
            result = subprocess.run(
                ["du", "-sb", str(data_dir)],
                capture_output=True,
                text=True,
                check=True,
            )
            size = int(result.stdout.split()[0])
            size_file.write_text(str(size))
            logger.info("Storage size updated: %d bytes", size)
        except Exception as e:
            stderr = getattr(e, "stderr", "") or ""
            logger.warning("du failed: %s%s", e, f" | stderr: {stderr.strip()}" if stderr.strip() else "")
        time.sleep(DU_INTERVAL)


def start_du_monitor(data_dir: Path, initial_delay: float = 0.0) -> None:
    """Start a daemon thread that periodically measures data_dir size."""
    if any(t.name == "du-monitor" for t in threading.enumerate()):
        logger.debug("du monitor thread already running, skipping")
        return

    thread = threading.Thread(
        target=_du_loop,
        args=(data_dir, initial_delay),
        daemon=True,
        name="du-monitor",
    )
    thread.start()
    logger.info("du monitor started (interval: %ds, initial delay: %.1fs)", DU_INTERVAL, initial_delay)
```

- [ ] **Step 4: Run delayed monitor tests**

Run:

```bash
uv run --package dashboard-api pytest dashboard/api/tests/unit/test_utils.py::TestDuMonitor -v
```

Expected: PASS.

- [ ] **Step 5: Run API startup tests that use `start_du_monitor()`**

Run:

```bash
uv run --package dashboard-api pytest dashboard/api/tests/unit/test_app_startup.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git add dashboard/api/utils.py dashboard/api/tests/unit/test_utils.py
git commit -m "perf(dashboard-api): Delay storage monitor scan" \
  -m "Allow the storage-size monitor to wait before the first du scan so PVC IO does not compete with first health responses."
```

## Task 4: Proxy Sidecar Waits For Real Health Endpoints

**Files:**
- Modify: `helm/charts/mddash/files/pre_spawn_hook.py`
- Create: `helm/charts/mddash/tests/test_pre_spawn_hook.py`

- [ ] **Step 1: Write failing proxy command test**

Create `helm/charts/mddash/tests/test_pre_spawn_hook.py` with:

```python
"""Tests for MDDash JupyterHub pre-spawn hook helpers."""

import builtins
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_pre_spawn_hook(monkeypatch):
    path = Path(__file__).parents[1] / "files" / "pre_spawn_hook.py"
    monkeypatch.setattr(
        builtins,
        "c",
        SimpleNamespace(KubeSpawner=SimpleNamespace()),
        raising=False,
    )
    spec = importlib.util.spec_from_file_location("pre_spawn_hook_under_test", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_proxy_start_command_waits_for_real_health_endpoints(monkeypatch) -> None:
    """Proxy startup should wait for successful auth and API health checks."""
    module = _load_pre_spawn_hook(monkeypatch)

    command = module._proxy_start_command("/user/alice")

    assert "curl --fail" in command
    assert "http://localhost:5001/health" in command
    assert "http://localhost:5000/user/alice/dash/api/health" in command
    assert "sleep 0.1" in command
    assert "caddy run --config /etc/caddy/Caddyfile --adapter caddyfile" in command
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest helm/charts/mddash/tests/test_pre_spawn_hook.py -v
```

Expected: FAIL because `_proxy_start_command()` does not exist.

- [ ] **Step 3: Extract proxy start command helper**

In `helm/charts/mddash/files/pre_spawn_hook.py`, add this helper above `_proxy_container()`:

```python
def _proxy_start_command(service_prefix: str) -> str:
    """Return the proxy startup command that waits for auth and API health."""
    api_health_url = f"http://localhost:5000{service_prefix}/dash/api/health"
    return (
        "until "
        "curl --fail --silent --show-error --connect-timeout 1 http://localhost:5001/health > /dev/null "
        f"&& curl --fail --silent --show-error --connect-timeout 1 {api_health_url} > /dev/null; "
        "do echo 'waiting for auth and dashboard API health'; sleep 0.1; done; "
        "exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile"
    )
```

Then change the `_proxy_container()` command field to:

```python
"command": ["sh", "-c", _proxy_start_command(service_prefix)],
```

- [ ] **Step 4: Run proxy command test**

Run:

```bash
uv run pytest helm/charts/mddash/tests/test_pre_spawn_hook.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

Run:

```bash
git add helm/charts/mddash/files/pre_spawn_hook.py helm/charts/mddash/tests/test_pre_spawn_hook.py
git commit -m "fix(spawner): Wait for dashboard sidecar health" \
  -m "Make the proxy sidecar wait for successful auth and dashboard API health responses instead of accepting any HTTP response from the ports."
```

## Task 5: Suppress Successful `mdrun-api` Health Access Logs

**Files:**
- Modify: `mdrun-api/Dockerfile`
- Create: `mdrun-api/tests/test_container_config.py`

- [ ] **Step 1: Write failing Dockerfile configuration test**

Create `mdrun-api/tests/test_container_config.py` with:

```python
"""Tests for mdrun-api container runtime configuration."""

from pathlib import Path


def test_uwsgi_suppresses_successful_health_access_logs() -> None:
    """Routine successful /api/health probes should not flood stdout logs."""
    dockerfile = Path(__file__).parents[1] / "Dockerfile"
    content = dockerfile.read_text()

    assert "--route-uri '^/api/health$ donotlog:'" in content
    assert "--log-4xx" in content
    assert "--log-5xx" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run --package mdrun-api pytest mdrun-api/tests/test_container_config.py -v
```

Expected: FAIL because the Dockerfile has no uWSGI health log filter.

- [ ] **Step 3: Add uWSGI health access-log filtering**

In `mdrun-api/Dockerfile`, replace the `CMD` with:

```dockerfile
CMD ["sh", "-c", "uwsgi --http 0.0.0.0:5000 --module app:app --processes $UWSGI_PROCESSES --threads $UWSGI_THREADS --enable-threads --master --die-on-term --route-uri '^/api/health$ donotlog:' --log-4xx --log-5xx 2>&1 | tee /data/api.log"]
```

This keeps failed 4xx/5xx requests visible while suppressing routine successful `/api/health` access lines.

- [ ] **Step 4: Run container config and route tests**

Run:

```bash
uv run --package mdrun-api pytest mdrun-api/tests/test_container_config.py mdrun-api/tests/test_routes.py::TestHealthEndpoint -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

Run:

```bash
git add mdrun-api/Dockerfile mdrun-api/tests/test_container_config.py
git commit -m "chore(mdrun-api): Suppress health probe access logs" \
  -m "Filter routine successful /api/health uWSGI access lines while preserving failed probe and error visibility."
```

## Task 6: Auth Startup Timing Logs

**Files:**
- Modify: `dashboard/auth/auth.py`
- Modify: `dashboard/auth/tests/test_auth.py`

- [ ] **Step 1: Write failing auth timing test**

Append this test to `dashboard/auth/tests/test_auth.py`:

```python
def test_health_logs_first_health_once(client: FlaskClient, caplog) -> None:
    """The first auth health response should be visible in startup diagnostics once."""
    caplog.set_level("INFO", logger="auth")

    client.get("/health")
    client.get("/health")

    messages = [record.getMessage() for record in caplog.records]
    assert messages.count("auth first health response served") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run --package dashboard-auth pytest dashboard/auth/tests/test_auth.py::test_health_logs_first_health_once -v
```

Expected: FAIL because auth does not log first health.

- [ ] **Step 3: Add lightweight auth startup logging**

In `dashboard/auth/auth.py`, add imports and module logger state:

```python
import logging
```

After `app = Flask(__name__)`, add:

```python
logger = logging.getLogger(__name__)
_first_health_logged = False
```

At the end of environment validation, add:

```python
logger.info("auth app initialized for user %s", USER)
```

Change `health()` to:

```python
@app.route("/health")
def health() -> tuple[str, int]:
    """Health check endpoint."""
    global _first_health_logged  # noqa: PLW0603
    if not _first_health_logged:
        logger.info("auth first health response served")
        _first_health_logged = True
    return "OK", HTTPStatus.OK
```

- [ ] **Step 4: Run auth tests**

Run:

```bash
uv run --package dashboard-auth pytest dashboard/auth/tests/test_auth.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 6**

Run:

```bash
git add dashboard/auth/auth.py dashboard/auth/tests/test_auth.py
git commit -m "chore(auth): Log first health response" \
  -m "Add one-time auth startup health visibility without logging every routine health probe."
```

## Task 7: Update Agent Documentation For New Startup Behavior

**Files:**
- Modify: `dashboard/api/AGENTS.md`
- Modify: `helm/charts/mddash/AGENTS.md`
- Modify: `mdrun-api/AGENTS.md`

- [ ] **Step 1: Update dashboard API AGENTS gotcha**

In `dashboard/api/AGENTS.md`, replace the Kubernetes resources gotcha line that says in-cluster config is called at module import with:

```markdown
- **In-cluster config is lazy-loaded**: `clients/k8s.py` initializes Kubernetes API clients on first Kubernetes operation, not during health-route import. Keep `/health` independent of Kubernetes setup so first-health latency remains low and failures are scoped to endpoints that need the cluster.
```

- [ ] **Step 2: Update Helm chart AGENTS proxy gotcha**

In `helm/charts/mddash/AGENTS.md`, add this gotcha under Sidecar Container Pattern or Critical Gotchas:

```markdown
- **Proxy Health Wait**: The proxy sidecar waits for `auth` `/health` and the dashboard API prefixed `/dash/api/health` endpoint with `curl --fail` before starting Caddy. Do not replace this with bare port checks; non-2xx responses must not count as readiness.
```

- [ ] **Step 3: Update mdrun-api AGENTS logging gotcha**

In `mdrun-api/AGENTS.md`, add this gotcha near SQLite or K8s config:

```markdown
- **Health access logs**: Successful `/api/health` probe access logs are suppressed at the uWSGI layer to avoid log congestion. Failed probes, 4xx/5xx responses, startup logs, and application errors must remain visible.
```

- [ ] **Step 4: Commit Task 7**

Run:

```bash
git add dashboard/api/AGENTS.md helm/charts/mddash/AGENTS.md mdrun-api/AGENTS.md
git commit -m "docs: Document dashboard startup behavior" \
  -m "Keep agent guidance aligned with lazy Kubernetes startup, proxy health waits, and mdrun-api health log filtering."
```

## Task 8: Full Verification And Final Commit If Needed

**Files:**
- No new files expected unless verification reveals fixes.

- [ ] **Step 1: Run dashboard API tests**

Run:

```bash
uv run --package dashboard-api pytest dashboard/api/tests -v
```

Expected: PASS.

- [ ] **Step 2: Run dashboard auth tests**

Run:

```bash
uv run --package dashboard-auth pytest dashboard/auth/tests -v
```

Expected: PASS.

- [ ] **Step 3: Run mdrun-api tests**

Run:

```bash
uv run --package mdrun-api pytest mdrun-api/tests -v
```

Expected: PASS.

- [ ] **Step 4: Run project format/type/test gate**

Run from repo root:

```bash
make format
make type-check
make test
```

Expected: all commands PASS.

- [ ] **Step 5: Render Helm values to catch template or hook syntax issues**

Run:

```bash
make -C helm render
```

Expected: PASS and no unintended generated value changes beyond normal render output.

- [ ] **Step 6: Inspect git status**

Run:

```bash
git status --short
```

Expected: clean working tree. If verification fixes were needed, commit them with a focused message:

```bash
git add <changed-files>
git commit -m "fix(startup): Address verification findings" \
  -m "Resolve issues found by the startup optimization verification gate."
```

## Manual Cluster Verification Checklist

Run after building/deploying to dev:

```bash
kubectl describe pod <user-pod> -n <user-namespace>
kubectl logs <user-pod> -n <user-namespace> -c api
kubectl logs <user-pod> -n <user-namespace> -c auth
kubectl logs <user-pod> -n <user-namespace> -c proxy
kubectl logs deploy/mdrun-api -n <hub-namespace>
```

Expected observations:

- API logs show startup phase durations.
- API does not log duplicate app construction or duplicate migration checks for one Gunicorn worker startup.
- Already-current DB logs `Database is at migration head ...; skipping upgrade`.
- Proxy logs show bounded waiting for auth/API health and then Caddy startup.
- `mdrun-api` logs no longer contain routine successful `/api/health` access lines.
- Failed or non-health requests still appear in `mdrun-api` logs.

## Plan Self-Review

- Spec coverage: Tasks cover API timing, single app construction, migration skip, lazy Kubernetes clients, delayed `du`, proxy health wait, `mdrun-api` health access-log filtering, docs, and verification.
- Placeholder scan: No deferred-decision markers, broad “handle errors” instructions, or undefined function names remain.
- Type consistency: New helper names are consistent across tests and implementation steps: `_run_migrations`, `get_core_v1`, `get_batch_v1`, `reset_k8s_clients_for_tests`, `_proxy_start_command`, and `start_du_monitor(initial_delay=...)`.
