# MDPosit Publishing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add MDPosit/MDDB as a stateless publication option alongside the existing InvenioRDM flow, and support importing experiments from MDPosit URLs via `Experiment.from_repo`.

**Architecture:** A new `clients/mdposit.py` module handles MDDB REST interaction for metadata and file listing/download. The publish route accepts `target` (`invenio` or `mdposit`). The Invenio path writes to the existing `mdrepo_id`/`mdrepo_published` columns unchanged. The MDPosit path is stateless: it generates metadata and file download URLs, returns them to the frontend, and does not persist any publication state. The import path extracts MDPosit URL detection and download into module-level helpers consumed by `Experiment.from_repo`. The frontend adds a target selector in the publish step and uses the existing `FileSelector` with extension filters.

**Tech Stack:** Flask, SQLAlchemy, Marshmallow, React, TanStack Query, ShadCN UI, Tailwind CSS, Playwright.

**Git note:** The task-level commit commands below are historical checkpoints from the planning format. Do not run commits unless the human explicitly asks for commits in the current session.

---

## Files overview

| File | Responsibility |
|---|---|
| `dashboard/api/clients/mdposit.py` | New client: `get_project`, `list_files`, `download_file`, `download_project`, URL helpers. |
| `dashboard/api/models/experiment.py` | Update `publish` method to route by target; keep Invenio body writing `mdrepo_id`/`mdrepo_published`; add `_publish_mdposit` validating selected handoff files and returning payload without DB writes. Extract `_import_invenio_repo` and `_import_mdposit_repo` module-level helpers consumed by `from_repo`. |
| `dashboard/api/schemas/experiment.py` | No changes required for publish state; keep existing serialization. |
| `dashboard/api/routes/experiments.py` | Accept `target` on publish; dispatch to existing Invenio publish or new MDPosit handoff. Update setup to use unified `from_repo` routing. |
| `dashboard/api/config.py` | Add normalized `MDPOSIT_URL`, `MDPOSIT_HOST`, `MDPOSIT_REST_URL`, `MDPOSIT_VRE_LITE_URL`; `MDPOSIT_TRUSTED_PARENT_HOST` (`mdposit.mddbr.eu`). |
| `config.yaml`, `config.dev.yaml`, `config.edc.yaml` | Add deploy-specific `mdposit.url`, for example `https://mdrepo.eu/`. |
| `helm/charts/mddash/values.yaml.tmpl` | Render `MDPOSIT_URL` into hub env. |
| `helm/charts/mddash/files/pre_spawn_hook.py` | Pass `MDPOSIT_URL` through to API sidecars. |
| `dashboard/api/clients/__init__.py` | Import and export `mdposit` module alongside existing clients. |
| `dashboard/api/pyproject.toml`, `uv.lock` | Add `pyyaml` only if metadata generation uses `yaml.dump`. |
| `dashboard/api/_demo/state.py` | Update demo state to include MDPosit import support. |
| `dashboard/api/_demo/seed.py` | Seed one experiment created from an MDPosit URL for demo. |
| `dashboard/ui/src/hooks/use-mdposit.ts` | New hook using `useMutation` for MDPosit publish handoff. |
| `dashboard/ui/src/components/Wizard/PublishStep/PublishStep.tsx` | Add target selector (default Invenio). Show Invenio UI unchanged. Show MDPosit handoff UI with FileSelector + download links + VRE Lite link. No accession linking or state tracking. |
| `dashboard/ui/src/pages/New.tsx` | Update help text to mention MDPosit/MDDB URLs in the DOI/repository field. |

---

### Task 1: Add MDPosit configuration

**Files:**
- Modify: `dashboard/api/config.py`
- Modify: `config.yaml`, `config.dev.yaml`, `config.edc.yaml`
- Modify: `helm/charts/mddash/values.yaml.tmpl`
- Modify: `helm/charts/mddash/files/pre_spawn_hook.py`

- [ ] **Step 1: Add MDPosit config**

After the MDREPO config block, add normalized URL derivation:

```python
from urllib.parse import urlparse

MDPOSIT_URL = os.environ.get("MDPOSIT_URL", "").rstrip("/")
MDPOSIT_HOST = urlparse(MDPOSIT_URL).netloc if MDPOSIT_URL else ""
MDPOSIT_REST_URL = f"{MDPOSIT_URL}/api/" if MDPOSIT_URL else ""
MDPOSIT_VRE_LITE_URL = f"{MDPOSIT_URL}/vre_lite/" if MDPOSIT_URL else ""
MDPOSIT_TRUSTED_PARENT_HOST = "mdposit.mddbr.eu"

if not MDPOSIT_URL:
    logger.warning("MDPOSIT_URL is not set. MDPosit integration will not be available.")
```

Add `mdposit.url` to each root config file and render it into the hub environment as `MDPOSIT_URL` in `values.yaml.tmpl`. Add `MDPOSIT_URL` to `_API_PASSTHROUGH_ENV` so spawned user API sidecars receive it.

- [ ] **Step 2: Commit**

```bash
git add dashboard/api/config.py config.yaml config.dev.yaml config.edc.yaml helm/charts/mddash/values.yaml.tmpl helm/charts/mddash/files/pre_spawn_hook.py
git commit -m "feat(api): add MDPosit URL configuration"
```

---

### Task 2: Create clients/mdposit.py

**Files:**
- Create: `dashboard/api/clients/mdposit.py`
- Modify: `dashboard/api/clients/__init__.py`

- [ ] **Step 1: Write client module**

```python
"""MDPosit/MDDB REST client."""

import logging
from http import HTTPStatus
from pathlib import Path
from shutil import copyfileobj
from urllib.parse import quote, urlparse

import requests
from config import MDPOSIT_HOST, MDPOSIT_REST_URL, MDPOSIT_TRUSTED_PARENT_HOST

logger = logging.getLogger(__name__)


def _api_url(path: str) -> str:
    return f"{MDPOSIT_REST_URL.rstrip('/')}/{path.lstrip('/')}"


def _project_url(accession: str, suffix: str = "") -> str:
    base = _api_url(f"projects/{accession}")
    if not suffix:
        return base
    suffix = suffix.lstrip("/")
    return f"{base}/{suffix}"


def get_project(accession: str) -> dict:
    """Fetch MDDB project metadata by accession or project ID.

    Args:
        accession: The project accession or ID.

    Returns:
        The project metadata as a dictionary.

    Raises:
        ValueError: If the project is not found.
        requests.HTTPError: If the request fails for any other reason.
    """
    response = requests.get(_project_url(accession), timeout=30)
    if response.status_code == HTTPStatus.NOT_FOUND:
        raise ValueError(f"Project {accession} not found on MDPosit")
    response.raise_for_status()
    return response.json()


def list_files(accession: str) -> list[str]:
    """List available file names for a project.

    Args:
        accession: The project accession or ID.

    Returns:
        A list of file names.

    Raises:
        requests.HTTPError: If the request fails.
    """
    response = requests.get(_project_url(accession, "files"), timeout=30)
    if response.status_code == HTTPStatus.NOT_FOUND:
        return []
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list):
        return [item["name"] if isinstance(item, dict) else str(item) for item in data]
    return []


def download_file(accession: str, filename: str, output_dir: Path) -> Path:
    """Download a specific project file.

    Args:
        accession: The project accession or ID.
        filename: The name of the file to download.
        output_dir: The directory to save the file to.

    Returns:
        The path to the downloaded file.

    Raises:
        requests.HTTPError: If the request fails.
    """
    safe_parts = [part for part in Path(filename).parts if part not in {"", "."}]
    if any(part == ".." for part in safe_parts):
        raise ValueError(f"Invalid MDPosit file path: {filename}")
    quoted_filename = "/".join(quote(part) for part in safe_parts)
    url = _project_url(accession, f"files/{quoted_filename}")
    output_path = output_dir.joinpath(*safe_parts)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=300, stream=True)
    response.raise_for_status()
    with output_path.open("wb") as f:
        copyfileobj(response.raw, f)
    return output_path


def download_project(accession: str, output_dir: Path) -> list[Path]:
    """Download all files for a project.

    Args:
        accession: The project accession or ID.
        output_dir: The directory to save the files to.

    Returns:
        A list of paths to the downloaded files.

    Raises:
        ValueError: If no files are found for the project.
        requests.HTTPError: If any download fails.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    filenames = list_files(accession)
    if not filenames:
        raise ValueError(f"No files found for project {accession}")
    return [download_file(accession, filename, output_dir) for filename in filenames]


def trusted_hosts() -> list[str]:
    """Return trusted MDPosit hostnames.

    Returns:
        Trusted hostname values, excluding empty config.
    """
    return [host for host in [MDPOSIT_TRUSTED_PARENT_HOST, MDPOSIT_HOST] if host]


def is_mdposit_url(url: str, hosts: list[str] | None = None) -> bool:
    """Check if a URL belongs to a trusted MDPosit host.

    Args:
        url: The URL to check.
        hosts: Optional list of trusted hostnames. Defaults to configured hosts.

    Returns:
        True if the URL's hostname is in the trusted hosts list.
    """
    host = urlparse(url).hostname or ""
    return host.lower() in {trusted_host.lower() for trusted_host in (hosts or trusted_hosts())}


def extract_accession(url: str) -> str:
    """Extract the accession or project ID from an MDPosit URL.

    Args:
        url: The MDPosit project URL.

    Returns:
        The last path segment as the accession.
    """
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1]
```

- [ ] **Step 2: Export from __init__.py**

Update `dashboard/api/clients/__init__.py`:

```python
"""Client modules for external services."""

from . import caddy, k8s, mdposit, mdrepo, mdrun, metadump, tuner

__all__ = ["caddy", "k8s", "mdposit", "mdrepo", "mdrun", "metadump", "tuner"]
```

- [ ] **Step 3: Commit**

```bash
git add dashboard/api/clients/mdposit.py dashboard/api/clients/__init__.py
git commit -m "feat(api): add MDPosit REST client with file download support"
```

---

### Task 3: Refactor experiment model for target-aware publish

**Files:**
- Modify: `dashboard/api/models/experiment.py`
- Modify: `dashboard/api/pyproject.toml`, `uv.lock` if using `PyYAML`

- [ ] **Step 1: Update module-level imports**

Update the existing import line:

```python
import yaml

from clients import mdposit, mdrepo, metadump
from validators import check_path
```

Add new config imports:

```python
from config import (
    API_PREFIX,
    DATA_DIR,
    MDPOSIT_VRE_LITE_URL,
    MDREPO_RECORD_NAME,
    MDREPO_URL,
)
```

- [ ] **Step 2: Update `publish` signature and route internally**

Change:
```python
def publish(self, community: str) -> dict:
```
to:
```python
def publish(
    self,
    target: str = "invenio",
    community: str = "ceitec",
    selected_files: dict[str, str] | None = None,
) -> dict:
```

Inside `publish`, add routing **before** the existing body:

```python
if target == "invenio":
    return self._publish_invenio(community)
if target == "mdposit":
    return self._publish_mdposit(selected_files or {})
raise BadRequest(description=f"Unknown publish target: {target}")
```

Rename the existing `publish` body to `_publish_invenio(self, community: str) -> dict`.

- [ ] **Step 3: Add `_publish_mdposit`**

Add a new method on `Experiment`:

```python
def _publish_mdposit(self, selected_files: dict[str, str]) -> dict:
    """Generate VRE Lite handoff payload without persisting any state.

    Args:
        selected_files: Mapping with structure, topology, and trajectory relative paths.

    Returns:
        A dict containing:
        - metadata_file: Metadata file path and download URL.
        - files: Selected MD file paths and download URLs.
        - vre_lite_url: The configured VRE Lite URL.

    Raises:
        BadRequest: If required files are missing or metadata generation fails.
    """
    exp_dir = DATA_DIR / self.id
    if not exp_dir.exists():
        raise BadRequest(description="Experiment directory not found.")

    required = {
        "structure": {"pdb", "gro"},
        "topology": {"top", "prmtop", "parm7", "psf"},
        "trajectory": {"xtc", "trr", "nc", "dcd"},
    }
    validated_files: dict[str, Path] = {}

    for role, allowed_extensions in required.items():
        relative_path = selected_files.get(role)
        if not relative_path:
            raise BadRequest(description=f"Missing MDPosit {role} file selection.")
        check_path(relative_path, exp_dir)
        file_path = exp_dir / relative_path
        if not file_path.is_file():
            raise BadRequest(description=f"Selected {role} file does not exist.")
        if file_path.suffix.lstrip(".").lower() not in allowed_extensions:
            raise BadRequest(description=f"Selected {role} file has an unsupported extension.")
        validated_files[role] = file_path

    metadata_path = exp_dir / "inputs.yaml"
    metadata = {
        "project": {
            "title": self.name,
            "description": self.source_message or "",
        },
        "files": {
            role: file_path.name for role, file_path in validated_files.items()
        },
    }
    try:
        with metadata_path.open("w", encoding="utf-8") as f:
            yaml.dump(metadata, f, default_flow_style=False, allow_unicode=True)
    except Exception as exc:
        raise InternalServerError(description=f"Failed to generate metadata file: {exc}") from exc

    return {
        "metadata_file": {
            "path": str(metadata_path.relative_to(DATA_DIR / self.id)),
            "url": f"{API_PREFIX}/experiments/{self.id}/files/{metadata_path.relative_to(DATA_DIR / self.id)}",
        },
        "files": [
            {
                "role": role,
                "path": str(file_path.relative_to(DATA_DIR / self.id)),
                "url": f"{API_PREFIX}/experiments/{self.id}/files/{file_path.relative_to(DATA_DIR / self.id)}",
            }
            for role, file_path in validated_files.items()
        ],
        "vre_lite_url": MDPOSIT_VRE_LITE_URL or None,
    }
```

**Note:** `PyYAML` is not declared in `dashboard/api/pyproject.toml` today. Either add `pyyaml` as an API dependency and update the lockfile, or replace this snippet with a minimal writer.

- [ ] **Step 4: Commit**

```bash
git add dashboard/api/models/experiment.py
git commit -m "feat(api): add target-aware publish routing in experiment model"
```

---

### Task 4: Refactor `Experiment.from_repo` to dispatch to Invenio and MDPosit helpers

**Files:**
- Modify: `dashboard/api/models/experiment.py`

- [ ] **Step 1: Extract `_import_invenio_repo` helper**

Extract the Invenio-specific logic from `from_repo` into a private module-level function. Place it above the `Experiment` class or at the bottom of the file following existing conventions.

```python
def _resolve_repo_link(repo_link: str) -> str:
    """Resolve DOI URLs to their final repository URL.

    Args:
        repo_link: DOI or repository URL.

    Returns:
        The normalized URL after DOI redirects when applicable.
    """
    resolved_link = repo_link.strip().rstrip("/")
    if urlparse(resolved_link).netloc == "doi.org":
        doi_response = requests.head(resolved_link, allow_redirects=True, timeout=30)
        resolved_link = doi_response.url.rstrip("/")
    return resolved_link


def _safe_extract_zip(zf: zipfile.ZipFile, output_dir: Path) -> None:
    """Extract a zip archive without allowing path traversal.

    Args:
        zf: Open zip file.
        output_dir: Destination directory.

    Raises:
        BadRequest: If the archive contains unsafe paths.
    """
    output_root = output_dir.resolve()
    for member in zf.infolist():
        target = (output_root / member.filename).resolve()
        if not str(target).startswith(str(output_root)):
            raise BadRequest(description="Repository archive contains an unsafe path.")
        zf.extract(member, output_root)


def _import_invenio_repo(repo_link: str, experiment_id: str) -> None:
    """Download an InvenioRDM repository archive and extract it into the experiment directory.

    Args:
        repo_link: The repository record URL.
        experiment_id: The local experiment ID.

    Raises:
        NotFound: If the repository is not found.
        InternalServerError: If the download or extraction fails.
    """
    parsed = urlparse(repo_link)
    path_parts = [p for p in parsed.path.split("/") if p]
    record_id: str = path_parts[-1]
    records_idx: int = path_parts.index("records")
    prefix_parts: list[str] = path_parts[:records_idx]
    api_segment: str = "/".join(prefix_parts) if prefix_parts else "records"
    url: str = f"{parsed.scheme}://{parsed.netloc}/api/{api_segment}/{record_id}/files-archive"

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)
        with requests.get(url, stream=True, timeout=300) as response:
            if response.status_code == HTTPStatus.NOT_FOUND:
                raise NotFound(description=f"Repository '{repo_link}' not found.")
            if response.status_code != HTTPStatus.OK:
                raise InternalServerError(
                    description=f"Failed to download repository: {response.status_code}"
                )
            for chunk in response.iter_content(chunk_size=128 * 1024):
                tmp_file.write(chunk)
        tmp_file.flush()
        with zipfile.ZipFile(tmp_path) as zf:
            _safe_extract_zip(zf, DATA_DIR / experiment_id)
    tmp_path.unlink(missing_ok=True)
```

- [ ] **Step 2: Add `_import_mdposit_repo` helper**

```python
def _import_mdposit_repo(repo_link: str, experiment_id: str) -> None:
    """Download all files from an MDPosit project into the experiment directory.

    Args:
        repo_link: The MDPosit project URL.
        experiment_id: The local experiment ID.

    Raises:
        BadRequest: If the URL is invalid or no files can be downloaded.
        InternalServerError: If a download fails.
    """
    accession = mdposit.extract_accession(repo_link)
    if not accession:
        raise BadRequest(description="Could not extract accession from MDPosit URL.")

    output_dir = DATA_DIR / experiment_id
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        mdposit.get_project(accession)
        with tempfile.TemporaryDirectory(dir=output_dir) as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            downloaded_files = mdposit.download_project(accession, tmp_dir)
            for downloaded_file in downloaded_files:
                target_path = output_dir / downloaded_file.relative_to(tmp_dir)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                downloaded_file.replace(target_path)
    except ValueError as exc:
        raise BadRequest(description=str(exc)) from exc
    except requests.HTTPError as exc:
        raise InternalServerError(description=f"Failed to download MDPosit project: {exc}") from exc
```

- [ ] **Step 3: Update `from_repo` dispatcher**

Replace the body of `from_repo` with:

```python
@classmethod
def from_repo(
    cls,
    name: str,
    repo_link: str,
    notebooks_repo: str,
    access_token: str | None = None,
    engine: Engine = Engine.GMX,
) -> "Experiment":
    """Create experiment from a repository URL (InvenioRDM or MDPosit).

    Args:
        name: Name of the experiment.
        repo_link: Repository record URL (InvenioRDM, Zenodo, MDPosit, or DOI).
        notebooks_repo: Git repository URL containing setup notebooks.
        access_token: Optional GitHub access token for private repositories.
        engine: Molecular dynamics engine (default: GMX).

    Returns:
        The created Experiment instance.

    Raises:
        NotFound: If the repository URL cannot be found.
        InternalServerError: If the repository download fails.
    """
    experiment_id: str = cls.prepare_env(notebooks_repo, access_token)

    try:
        resolved_repo_link = _resolve_repo_link(repo_link)
        if mdposit.is_mdposit_url(resolved_repo_link):
            _import_mdposit_repo(resolved_repo_link, experiment_id)
        else:
            _import_invenio_repo(resolved_repo_link, experiment_id)

        message: str = f"Created by downloading repository from '{repo_link}'."
        experiment = cls(
            id=experiment_id, name=name, source_message=message, notebooks_repo=notebooks_repo, engine=engine
        )

        return cls._create_with_notebook(experiment)

    except Exception:
        rmtree(DATA_DIR / experiment_id, ignore_errors=True)
        db.session.rollback()
        raise
```

- [ ] **Step 4: Commit**

```bash
git add dashboard/api/models/experiment.py
git commit -m "feat(api): dispatch from_repo to Invenio and MDPosit helpers"
```

---

### Task 5: Update publish route for target selection

**Files:**
- Modify: `dashboard/api/routes/experiments.py`

- [ ] **Step 1: Accept `target` in publish endpoint**

```python
@experiments_bp.route("/<experiment_id>/publish", methods=["POST"])
@handle_exceptions(rollback=True)
def publish_experiment(experiment_id: str) -> ResponseReturnValue:
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    data = request.get_json(silent=True) or {}
    target = data.get("target", "invenio")

    if target == "invenio":
        token_manager = MDRepoTokenManager(session)
        token = token_manager.get_valid_token()
        if not token:
            raise Unauthorized("Not authenticated with MDRepo. Please authenticate first.")
        result = experiment.publish(target="invenio", community="ceitec")
    elif target == "mdposit":
        selected_files = data.get("files")
        if not isinstance(selected_files, dict):
            raise BadRequest("MDPosit publish requires selected files.")
        result = experiment.publish(target="mdposit", selected_files=selected_files)
    else:
        raise BadRequest(f"Unknown publish target: {target}")

    return jsonify(result), HTTPStatus.CREATED
```

There is **no accession linking endpoint** for MDPosit because MDDash does not track MDPosit publication state. MDRepo OAuth remains required only for the Invenio target.

- [ ] **Step 2: Commit**

```bash
git add dashboard/api/routes/experiments.py
git commit -m "feat(api): add target-aware publish endpoint"
```

---

### Task 6: Frontend target selector and handoff UI (no state tracking)

**Files:**
- Modify: `dashboard/ui/src/components/Wizard/PublishStep/PublishStep.tsx`
- Create: `dashboard/ui/src/hooks/use-mdposit.ts`

- [ ] **Step 1: Add hook for MDPosit publish handoff** using `useMutation`

```typescript
// dashboard/ui/src/hooks/use-mdposit.ts
import { useMutation } from "@tanstack/react-query"
import { api } from "@/lib/http"

export interface MdPositHandoffFile {
  role: "structure" | "topology" | "trajectory"
  path: string
  url: string
}

export interface MdPositHandoffResponse {
  metadata_file: { path: string; url: string }
  files: MdPositHandoffFile[]
  vre_lite_url: string | null
}

interface MdPositSelectedFiles {
  structure: string
  topology: string
  trajectory: string
}

export function useMdPositPublishData(experimentId: string) {
  return useMutation<MdPositHandoffResponse, Error, MdPositSelectedFiles>({
    mutationFn: (files) =>
      api.post(`/experiments/${experimentId}/publish`, { target: "mdposit", files }).then((r) => r.data),
  })
}
```

- [ ] **Step 2: Render target selector in PublishStep**

Add a `Select` with options `["invenio", "mdposit"]` defaulting to `"invenio"`.
Keep existing Invenio UI logic unchanged.
If target is `mdposit`, render:
- Three `FileSelector` controls: structure (`pdb`, `gro`), topology (`top`, `prmtop`, `parm7`, `psf`), and trajectory (`xtc`, `trr`, `nc`, `dcd`). The existing `FileSelector` is single-select, so this plan supports one trajectory file.
- Instructions for opening VRE Lite.
- Link from the backend `vre_lite_url` when present.
- Individual download links for metadata and selected files. Prefer `<a download>` so text/YAML files download instead of opening inline.

Keep the existing Invenio `usePublishExperiment` behavior and `mdrepo_id` cache update only inside the Invenio branch. The MDPosit branch must not update `experiment.mdrepo_id`, `mdrepo_record_url`, `mdrepo_published`, or wizard step state.

Do **not** render an accession input or any follow-up state tracking for MDPosit.

- [ ] **Step 3: Commit**

```bash
git add dashboard/ui/src/hooks/use-mdposit.ts dashboard/ui/src/components/Wizard/PublishStep/PublishStep.tsx
git commit -m "feat(ui): add MDPosit publish target selector and handoff UI"
```

---

### Task 7: Update demo harness for MDPosit

**Files:**
- Modify: `dashboard/api/_demo/state.py`, `dashboard/api/_demo/seed.py`, `dashboard/api/_demo/mocks/http.py`, `dashboard/api/_demo/files.py`

- [ ] **Step 1: Add MDPosit demo mock**

In `_demo/state.py`, add `mdposit_projects` dict with a fake accession for import lookup, and mock `list_files`/`download_file` behavior.
In `seed.py`, seed one experiment created from an MDPosit URL.
In `_demo/mocks/http.py`, add deterministic MDPosit API mocks for `GET /api/projects/{id}`, `GET /api/projects/{id}/files`, and `GET /api/projects/{id}/files/{filename}` instead of relying on the current MDPosit pass-through for this flow. Use fixtures from `_demo/files.py` so `make demo` works offline.

- [ ] **Step 2: Commit**

```bash
git add dashboard/api/_demo/state.py dashboard/api/_demo/seed.py
git commit -m "feat(demo): add MDPosit demo data and mocks"
```

---

### Task 8: Add/update backend tests

**Files:**
- Modify: `dashboard/api/tests/unit/test_mdrepo_routes.py` (or new `test_mdposit.py`)

- [ ] **Step 1: Add tests**

Tests to cover:
- Default publish target is Invenio (`publish` gets `"invenio"` by default) and still requires MDRepo OAuth.
- Explicit `target=mdposit` returns handoff data without requiring MDRepo OAuth.
- MDPosit publish does **not** modify `mdrepo_id` or `mdrepo_published`.
- Existing Invenio publish behavior remains unchanged.
- MDPosit handoff uses the user-selected structure, topology, and trajectory files only.
- Missing selected file, nonexistent selected file, unsupported extension, and traversal paths return useful errors.
- MDPosit URL detection and accession extraction.
- MDPosit metadata lookup and file-list/download failure.
- `_import_mdposit_repo(...)` creates an experiment when MDPosit files are available.
- Config derivation for MDPosit URLs.
- Helm/pre-spawn rendering passes `MDPOSIT_URL` to API sidecars.

- [ ] **Step 2: Run tests**

```bash
cd dashboard/api && pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add dashboard/api/tests
git commit -m "test(api): add MDPosit publish, import, and client tests"
```

---

### Task 9: Run fix, type-check, and full test suite

- [ ] **Step 1: Run code quality checks**

```bash
make fix
make type-check
make test
```

Expected: all pass.

- [ ] **Step 2: Commit any auto-format changes**

```bash
git add -A && git commit -m "style: apply fixes after MDPosit implementation"
```

---

## Self-Review

**1. Spec coverage:**
- Publish target selector: Task 6
- FileSelector with extension filters: Task 6
- Individual file downloads vs zip package: Tasks 3, 6
- Invenio publish unchanged: implicit in Task 3 routing
- MDPosit publish handoff (metadata + VRE Lite link): Tasks 2, 3, 6
- MDPosit import via `from_repo`: Task 4
- Config simplification (`mdpositUrl` only): Task 1
- Equal treatment of Invenio/MDPosit import helpers: Task 4
- Demo support: Task 7
- Frontend demo with Playwright: not a code task, but final approach.

**2. Coding standards compliance:**
- No wildcard imports: explicit module imports in `__init__.py`.
- No imports inside functions: all imports at module level.
- `pathlib` used for all file operations (`Path.open`, `Path.mkdir`, ` Path.unlink`).
- `useMutation` used for the POST-based publish handoff, not `useQuery` with `enabled: false`.
- Proper Google-style docstrings on all new functions.
- Type hints on all function signatures.
- `shutil.copyfileobj` for streaming downloads instead of manual chunk loops.
- `list_files` handles both string lists and dict lists from the API.
- `_project_url` avoids double slashes via `lstrip("/")`.
- Module-level helpers (`_import_invenio_repo`, `_import_mdposit_repo`) keep `from_repo` readable.
- Error handling uses werkzeug exceptions (`BadRequest`, `InternalServerError`, `NotFound`) consistent with existing routes.

**3. Placeholder scan:**
- No `TODO`/`TBD` left; all client functions are fully implemented.
- All code snippets are real code (not pseudocode).

**4. Type consistency:**
- No new DB columns; `mdrepo_id`/`mdrepo_published` remain unchanged for Invenio.
- MDPosit publish is stateless and returns dict from model method.
