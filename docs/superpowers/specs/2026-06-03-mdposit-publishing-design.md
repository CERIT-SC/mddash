# MDPosit Publishing Design

## Context

MDDash currently supports publication through an InvenioRDM-compatible integration that is still named MDRepo in parts of the code and UI. That legacy MDRepo label means the current Invenio draft-deposition flow; it does not mean `mdrepo.eu` in this design. The current flow creates an Invenio draft deposition, uploads files directly to that draft, stores the draft/record identifier locally (`mdrepo_id`/`mdrepo_published`), and opens the Invenio draft UI so the user can complete metadata and explicitly publish.

MDPosit, backed by MDDB, is not an Invenio draft-deposition backend. The verified MDDB/VRE Lite flow is an upload and staging helper: users provide metadata, upload structure/topology/trajectory files through VRE Lite, and MDDB workflow/loader processes create the final MDPosit project later. The public MDDB REST API is read/query oriented and does not expose a publish/deposition endpoint.

The MDPosit/MDDB target deployment is:

- Client: `https://mdrepo.eu/`
- REST API: `https://mdrepo.eu/api/`
- VRE Lite: `https://mdrepo.eu/vre_lite/`

Terminology used in this design:

- Invenio target means the existing InvenioRDM draft-deposition flow. Some current code and UI names this MDRepo; that is legacy naming.
- `mdrepo.eu` is not the existing Invenio target. In this design, `mdrepo.eu` is the MDPosit deployment containing the MDDB backend, MDDB REST API, and VRE Lite.
- MDDB/MDPosit target means the MDPosit flow exposed through MDDB REST and VRE Lite.

## Goals

- Keep the existing Invenio publication flow unchanged and make it the default publish target.
- Add MDPosit/MDDB as a second publish option in the publish step.
- Make MDPosit publishing an honest guided handoff to VRE Lite, not a fake automated publish.
- Let users import/create a MDDash experiment from an existing MDPosit record URL/accession through the existing DOI/repository setup field.
- Update the demo harness so the new flows can be exercised locally.

## Non-Goals

- Do not run MDDB workflow or loader commands from MDDash.
- Do not add SSH, VPN, or remote-command automation to the MDPosit host.
- Do not upload to VRE Lite programmatically from MDDash. The user uploads the prepared files through the VRE Lite browser UI.
- Do not claim an MDPosit project is published until a final accession/project ID is verified.
- Do not integrate directly with MDPosit storage for publish or import in this design.
- Do not store or require MDPosit host, storage, database, or remote execution credentials in MDDash.
- Do not track MDPosit publication state in the MDDash database. The flow ends when MDDash hands the files to the user.

## Architecture

The publish route accepts a `target` value with `invenio` as the default and `mdposit` as the second option. The Invenio target requires the existing MDRepo OAuth token. The MDPosit target must not require MDRepo OAuth because it is a local file handoff, not an authenticated repository deposition.

The existing Invenio path remains the default behavior. It keeps using the current MDRepo-named OAuth/client code for Invenio draft deposition creation, file upload, local record storage (`mdrepo_id`/`mdrepo_published`), and redirect/open behavior for the Invenio draft UI. That MDRepo-named code should not be confused with the `mdrepo.eu` MDPosit deployment. No database schema changes are required for the Invenio target.

MDPosit/MDDB uses a guided manual handoff. The user selects the structure, topology, and trajectory files that should be handed off. MDDash validates those selected paths, generates a VRE Lite-compatible metadata file, and provides direct download links for the metadata file and the selected MD files required by the VRE Lite upload steps. The user opens `https://mdrepo.eu/vre_lite/`, uploads the metadata file first, reviews or fills the VRE Lite form, and uploads the prepared MD files through VRE Lite.

MDDash does not record MDPosit handoff or publication state. The endpoint returns the prepared files and a VRE Lite URL; the flow ends there.

Setup import remains one DOI/repository URL field. DOI and InvenioRDM URLs use the existing archive download path. Trusted MDPosit URLs, including `mdposit.mddbr.eu` and the configured MDPosit host such as `mdrepo.eu`, route through the MDPosit client to fetch metadata and download record files from official MDDB REST/client endpoints.

## Backend Components

- `clients/mdposit.py`: function-based MDPosit client module, parallel to `clients/mdrepo.py`.
- `clients/mdposit.py:get_project(...)`: fetch MDDB project metadata by accession/project ID.
- `clients/mdposit.py:list_files(...)`: list available files for a project via `GET /projects/{id}/files`.
- `clients/mdposit.py:download_file(...)`: download a specific project file via `GET /projects/{id}/files/{filename}`.
- `clients/mdposit.py:download_project(...)`: orchestrates listing and downloading all project files to a local directory.
- `clients/mdposit.py` URL helpers: detect trusted MDPosit hosts and extract accession/project IDs.
- Publish route/model functions: short target-specific functions such as `publish_invenio(...)` and `publish_mdposit(...)` or equivalent module-level methods.
- Repo import helpers: keep `Experiment.from_repo(...)` as the single setup entry point for all repository/DOI URLs. It routes to `import_invenio_repo(...)` or `import_mdposit_repo(...)` depending on URL detection.
- `import_invenio_repo(...)`: helper that downloads the InvenioRDM `files-archive` and returns the files needed for `Experiment.from_repo(...)`.
- `import_mdposit_repo(...)`: helper that fetches MDPosit metadata and downloads all project files for `Experiment.from_repo(...)`.
- Handoff helper: validates user-selected file paths, generates the VRE Lite metadata file, and serves the metadata and required MD files as individual downloads with a short instruction file.

Avoid a new class-heavy abstraction. The existing API uses function modules and model methods; the implementation should stay consistent with that style.

## Database Changes

None for MDPosit publish. The existing Invenio target continues to use `mdrepo_id` and `mdrepo_published` unchanged.

MDPosit import creates an experiment the same way any other `from_repo` source does. No additional source-provenance columns are added.

## Frontend Components

- Publish step target selector, defaulting to the existing Invenio target.
- Invenio UI state remains functionally unchanged: OAuth connect, publish, and view/edit draft.
- MDPosit UI state explains the handoff clearly.
- MDPosit file selection UI lets the user pick one structure file, one topology file, and one trajectory file from the experiment directory using the existing `FileSelector` with extension filters. Multi-trajectory handoff is deferred unless a multi-select file picker is added.
- MDPosit handoff action provides individual download links for the selected metadata file and selected MD files.
- MDPosit instructions tell the user to open VRE Lite, upload the metadata file first, review the metadata form, then upload structure/topology/trajectory files.
- Setup page keeps the existing DOI/repository field and expands help text to mention MDPosit/MDDB URLs.

## MDPosit Publish Flow

1. User opens the publish step.
2. Target selector defaults to the existing Invenio target.
3. User selects MDPosit/MDDB.
4. Backend validates that MDDash can create a VRE Lite-compatible metadata file.
5. UI presents `FileSelector` controls filtered to relevant extensions so the user can choose one structure, one topology, and one trajectory file for handoff.
6. Backend validates the selected paths and generates the VRE Lite metadata file.
7. UI provides individual download links for:
   - VRE Lite metadata file.
   - User-selected structure file.
   - User-selected topology file.
   - User-selected trajectory file.
8. UI also provides a link to `https://mdrepo.eu/vre_lite/` and short instructions.
9. User opens VRE Lite manually and completes upload and metadata review.

MDDash does not track, store, or follow up on the MDPosit handoff.

## Invenio Publish Flow

1. User keeps the default Invenio target.
2. Existing OAuth status check runs.
3. Existing draft deposition creation runs.
4. Existing file upload worker runs.
5. Existing local record state (`mdrepo_id`/`mdrepo_published`) is stored as it is today.
6. UI opens the Invenio draft edit URL as it does today.

This flow must remain behaviorally unchanged for users.

## MDPosit Import Flow

1. User enters a DOI/repository URL in the existing setup field.
2. Resolver follows DOI redirects when needed.
3. `Experiment.from_repo(...)` detects whether the URL is an InvenioRDM record or a trusted MDPosit host.
4. If InvenioRDM, `import_invenio_repo(...)` downloads the `files-archive` and returns the files needed for experiment creation.
5. If MDPosit, `import_mdposit_repo(...)` extracts the accession/project ID, fetches metadata from configured MDDB REST, lists files via `GET /projects/{id}/files`, downloads each file via `GET /projects/{id}/files/{filename}`, and returns the files/metadata needed for experiment creation.
6. `Experiment.from_repo(...)` creates the experiment from the downloaded files.
7. The new experiment stores the original source URL for display, the same way other experiment sources are tracked.

If MDDB returns metadata but any file download fails, MDDash returns a clear error and does not create a partial experiment.

## Configuration

Add or clarify configuration values in `config.yaml` and environment rendering:

- `mdpositUrl`: base MDPosit client URL, for example `https://mdrepo.eu/`. The REST API URL and VRE Lite URL are derived from this as `<mdpositUrl>/api/` and `<mdpositUrl>/vre_lite/` respectively after normalizing the base URL to avoid duplicate slashes.
- Trusted parent host: hardcode `mdposit.mddbr.eu` as a trusted MDPosit parent repository host.
- Configured MDPosit host: derive the deploy-specific trusted host, such as `mdrepo.eu`, from the hostname portion of `mdpositUrl`.
- Deployment propagation: render `mdpositUrl` into the API sidecar as `MDPOSIT_URL` through the Helm values template and pre-spawn hook environment passthrough.

If legacy `MDREPO_*` environment names remain in code, keep them scoped to the existing Invenio integration or introduce clearer Invenio aliases during implementation. Do not point legacy Invenio/MDRepo config at `mdrepo.eu`; `mdrepo.eu` belongs to the MDPosit/MDDB configuration above.

Do not configure MDPosit storage credentials for this flow. MDDash uses VRE Lite as a user-facing handoff UI and MDDB REST/client endpoints for record lookup/import only.

## Error Handling

Invenio errors keep the current semantics: missing OAuth returns unauthorized, draft creation and upload failures return API errors, and failed upload does not mark the experiment published.

MDPosit errors are local and explicit:

- Missing metadata mapping or user-selected files returns a validation error describing what is missing.
- File preparation or handoff failure does not update any experiment state.
- Missing VRE Lite URL still allows metadata generation and file download, but the UI does not show an "Open VRE Lite" action.
- Import fails without creating an experiment if metadata is found but any record file cannot be downloaded.
- MDPosit publish never fails because the user is not authenticated with the legacy MDRepo/Invenio OAuth integration; that authentication applies only to the Invenio target.

## Demo Support

Update `dashboard/api/_demo/` as needed:

- Demo mocks should simulate MDPosit metadata lookup and file download for import.
- Demo seed data should include at least one experiment created from an MDPosit URL.
- Demo publish flow should allow exercising MDPosit file handoff without real MDPosit calls.

## Testing And Verification

Backend unit tests should cover:

- Default publish target is Invenio.
- Explicit `target=mdposit` returns handoff data.
- Existing Invenio publish behavior remains unchanged.
- MDPosit handoff provides metadata and required file downloads.
- Missing-file validation returns useful errors.
- MDPosit URL detection and accession extraction.
- MDPosit metadata lookup and file-list/download failure.
- `import_mdposit_repo(...)` creates an experiment when MDPosit files are available.
- Config derivation for MDPosit URLs.

Frontend behavior should be verified through the demo instead of assuming a frontend test framework:

1. Run `make demo`.
2. Use the Playwright/browser MCP to exercise the publish selector.
3. Verify Invenio remains the default and still shows current OAuth/publish behavior.
4. Verify MDPosit file downloads, VRE Lite link, and setup import paths.

Final implementation verification should run from the repository root:

```bash
make fix
make type-check
make test
```

## Open Constraints

- Full automated MDPosit publication is not part of this design because the verified VRE Lite upload API does not link server-side uploads to a browser handoff and MDDB REST does not expose a publish endpoint.
- The metadata mapping from MDDash experiment data to VRE Lite metadata should be conservative. Fields that cannot be mapped confidently should be left for the user to review or fill in VRE Lite.
