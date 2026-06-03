# MDPosit Publishing Design

## Context

MDDash currently supports publication through an InvenioRDM-compatible MDRepo integration. The current flow creates an Invenio draft deposition, uploads files directly to that draft, stores the draft/record identifier locally, and opens the Invenio draft UI so the user can complete metadata and explicitly publish.

MDPosit, backed by MDDB, is not an Invenio draft-deposition backend. The verified MDDB/VRE Lite flow is an upload and staging helper: users provide metadata, structure/topology/trajectory files are uploaded through VRE Lite or MinIO-compatible storage, and MDDB workflow/loader processes create the final MDPosit project later. The public MDDB REST API is read/query oriented and does not expose a publish/deposition endpoint.

The target deployment is:

- Client: `https://mdrepo.eu/`
- REST API: `https://mdrepo.eu/api/`
- VRE Lite: `https://mdrepo.eu/vre_lite/`
- S3/MinIO API: `https://s3.mdrepo.eu/`

Terminology used in this design:

- MDRepo means the existing InvenioRDM flow.
- MDDB/MDPosit means the MDPosit flow exposed through MDDB REST and VRE Lite.

## Goals

- Keep Invenio/MDRepo publication unchanged and make it the default publish target.
- Add MDPosit/MDDB as a second publish target in the publish step.
- Make MDPosit publishing an honest guided handoff to VRE Lite, not a fake automated publish.
- Let users import/create a MDDash experiment from an existing MDPosit record URL/accession through the existing DOI/repository setup field.
- Add simple target-aware publication state and source provenance.
- Keep credentials server-side and avoid exposing permanent MDPosit, MinIO, MongoDB, or host credentials to the browser.
- Update the demo harness so the new flows can be exercised locally.

## Non-Goals

- Do not run MDDB workflow or loader commands from MDDash.
- Do not add SSH, VPN, or remote-command automation to the MDPosit host.
- Do not call VRE Lite `/api/upload` from MDDash for the initial publish flow. The endpoint exists, but it is fire-and-forget staging and cannot be linked to a redirected browser session.
- Do not claim an MDPosit project is published until a final accession/project ID is verified.
- Do not expose MinIO internals to end users for import.

## Architecture

Publication becomes target-aware. The publish route accepts a `target` value with `invenio` as the default and `mdposit` as the second option.

The existing Invenio/MDRepo path remains the default behavior. It keeps using MDRepo OAuth, draft deposition creation, file upload, local record storage, and redirect/open behavior for the Invenio draft UI.

MDPosit/MDDB uses a guided manual handoff. MDDash prepares a VRE Lite-compatible export: the metadata file is the main artifact, and the export also includes the structure/topology/trajectory files needed by the VRE Lite upload steps. The user downloads the export, opens `https://mdrepo.eu/vre_lite/`, uploads the metadata file first, reviews or fills the VRE Lite form, and uploads the prepared MD files through VRE Lite.

MDDash records this as an export/handoff state. It does not store VRE Lite bucket state because MDDash is not creating the VRE Lite upload. It stores a final MDPosit accession only after the user links an accession and MDDash verifies it through the configured MDDB REST API.

Setup import remains one DOI/repository URL field. DOI and InvenioRDM URLs use the existing archive download path. Trusted MDPosit URLs, including `mdposit.mddbr.eu` and the configured MDPosit host such as `mdrepo.eu`, route through the MDPosit client to fetch metadata and download record files from official MDDB endpoints when available.

## Backend Components

- `clients/mdposit.py`: function-based MDPosit client module, parallel to `clients/mdrepo.py`.
- `clients/mdposit.py:get_project(...)`: fetch MDDB project metadata by accession/project ID.
- `clients/mdposit.py:download_project(...)`: download files for an MDPosit record when an official endpoint is available.
- `clients/mdposit.py` URL helpers: detect trusted MDPosit hosts and extract accession/project IDs.
- Publish route/model functions: short target-specific functions such as `publish_invenio(...)` and `publish_mdposit(...)` or equivalent module-level functions.
- `Experiment.from_mdposit(...)`: create a new experiment from an MDPosit record after metadata and files are downloaded.
- Export helper: builds the MDPosit export package with the VRE Lite metadata file, selected MD files, and a short instruction file.

Avoid a new class-heavy abstraction. The existing API uses function modules and model methods; the implementation should stay consistent with that style.

## Database Changes

The current `mdrepo_id` and `mdrepo_published` fields are too narrow for two targets. Add a migration with simple target-aware fields.

Proposed publication fields:

- `publish_target`: nullable string, values `invenio` or `mdposit`.
- `publish_status`: nullable string, values such as `draft`, `exported`, `published`.
- `publish_id`: nullable string, Invenio record/draft ID or final MDPosit accession.
- `publish_url`: nullable string, final external project/draft URL when known.

Proposed source provenance fields:

- `source_type`: nullable string, values such as `pdb`, `repo`, `file`, `mdposit`.
- `source_id`: nullable string, such as a PDB ID or MDPosit accession.
- `source_url`: nullable string, original source URL when applicable.

Migration behavior:

- Existing `mdrepo_id` values migrate to `publish_id` with `publish_target='invenio'`.
- Existing `mdrepo_published=True` migrates to `publish_status='published'`.
- Existing `mdrepo_published=False` migrates to `publish_status='draft'`.
- Legacy fields may remain temporarily if that is the least disruptive path, but new code should use the target-aware fields.

## Frontend Components

- Publish step target selector, defaulting to Invenio/MDRepo.
- Invenio UI state remains functionally unchanged: OAuth connect, publish, and view/edit draft.
- MDPosit UI state explains the handoff clearly.
- MDPosit export action downloads the package generated by MDDash.
- MDPosit instructions tell the user to open VRE Lite, upload the metadata file first, review the metadata form, then upload structure/topology/trajectory files.
- MDPosit accession-linking UI lets the user enter the final accession after MDPosit processing completes.
- Setup page keeps the existing DOI/repository field and expands help text to mention MDPosit/MDDB URLs.

## MDPosit Publish Flow

1. User opens the publish step.
2. Target selector defaults to Invenio/MDRepo.
3. User selects MDPosit/MDDB.
4. Backend validates that MDDash can create a VRE Lite-compatible metadata file and identify the MD files required for handoff.
5. Backend creates an export package named with Jupyter user, experiment ID, and date, for example `<user>-<experiment_id>-<YYYYMMDD>-mdposit.zip`.
6. Export package contains:
   - VRE Lite metadata file.
   - Structure file when available or required by the VRE Lite metadata flow.
   - Topology file.
   - Trajectory file or files.
   - `README.txt` with VRE Lite upload instructions.
7. MDDash marks local state as `publish_target='mdposit'` and `publish_status='exported'` after successful export generation.
8. UI gives the user the package download and a link to `https://mdrepo.eu/vre_lite/`.
9. User completes upload and metadata review in VRE Lite manually.
10. After MDPosit processing creates a project, user links the final accession in MDDash.
11. MDDash verifies the accession via MDDB REST and stores `publish_id`, `publish_url`, and `publish_status='published'`.

## Invenio Publish Flow

1. User keeps the default Invenio/MDRepo target.
2. Existing OAuth status check runs.
3. Existing draft deposition creation runs.
4. Existing file upload worker runs.
5. Existing local record state is stored through the new target-aware fields.
6. UI opens the Invenio draft edit URL as it does today.

This flow must remain behaviorally unchanged for users.

## MDPosit Import Flow

1. User enters a DOI/repository URL in the existing setup field.
2. Resolver follows DOI redirects when needed.
3. If the URL is an InvenioRDM record, existing `Experiment.from_repo(...)` runs.
4. If the URL host is `mdposit.mddbr.eu` or the configured MDPosit host, MDDash extracts the accession/project ID.
5. `clients/mdposit.py` fetches project metadata from configured MDDB REST.
6. `clients/mdposit.py` downloads the project files from official MDDB endpoints when available.
7. `Experiment.from_mdposit(...)` creates the experiment from the downloaded files.
8. The new experiment stores `source_type='mdposit'`, `source_id=<accession>`, and `source_url=<original URL>`.

If the public MDDB API can return metadata but cannot return downloadable files for a record, MDDash returns a clear error and does not create a partial experiment.

## Configuration

Add or clarify configuration values in `config.yaml` and environment rendering:

- `mdpositUrl`: base MDPosit client URL, for example `https://mdrepo.eu/`.
- `mdpositRestUrl`: REST API URL, default derived from `mdpositUrl` as `<mdpositUrl>/api/` when not explicitly set.
- `mdpositVreLiteUrl`: VRE Lite URL, default derived from `mdpositUrl` as `<mdpositUrl>/vre_lite/` when not explicitly set.
- Trusted parent host: hardcode `mdposit.mddbr.eu` as a trusted MDPosit parent repository host.
- Configured MDPosit host: derive the deploy-specific trusted host, such as `mdrepo.eu`, from `mdpositUrl`.

Do not configure permanent browser-visible MinIO credentials for this flow.

## Error Handling

Invenio errors keep the current semantics: missing OAuth returns unauthorized, draft creation and upload failures return API errors, and failed upload does not mark the experiment published.

MDPosit errors are local and explicit:

- Missing metadata mapping or required MD files returns a validation error describing what is missing. Structure is included when available or required by the VRE Lite metadata flow; topology and trajectory files are the primary MD upload files.
- Export package creation failure does not update publication state.
- Missing VRE Lite URL still allows package generation, but the UI does not show an “Open VRE Lite” action.
- Accession linking verifies the MDPosit project before storing it.
- Import fails without creating an experiment if metadata is found but record files cannot be downloaded.

State semantics:

- `exported`: MDDash generated the MDPosit handoff package.
- `draft`: Invenio draft exists.
- `published`: final external record/accession is verified.

## Demo Support

Update `dashboard/api/_demo/` as needed:

- Demo state should include Invenio and MDPosit publication statuses.
- Demo mocks should simulate MDPosit metadata lookup and file download for import.
- Demo seed data should include at least one MDPosit-linked or imported experiment.
- Demo publish flow should allow exercising MDPosit export and accession linking without real MDPosit calls.

## Testing And Verification

Backend unit tests should cover:

- Default publish target is Invenio.
- Explicit `target=mdposit` routes to MDPosit export.
- Existing Invenio publish behavior remains unchanged.
- MDPosit export package includes metadata, required files, and instructions.
- Missing-file validation returns useful errors.
- Migration maps existing MDRepo fields to target-aware fields.
- MDPosit URL detection and accession extraction.
- MDPosit metadata lookup, file download success, provenance storage, and file-download-unavailable failure.
- Config derivation for MDPosit URLs.

Frontend behavior should be verified through the demo instead of assuming a frontend test framework:

1. Run `make demo`.
2. Use the Playwright/browser MCP to exercise the publish selector.
3. Verify Invenio remains the default and still shows current OAuth/publish behavior.
4. Verify MDPosit export/download, VRE Lite link, accession linking, and setup import paths.

Final implementation verification should run from the repository root:

```bash
make fix
make type-check
make test
```

## Open Constraints

- Full automated MDPosit publication is not part of this design because the verified VRE Lite upload API does not link server-side uploads to a browser handoff and MDDB REST does not expose a publish endpoint.
- MDPosit import depends on official MDDB download support. If record files are not available through public/official endpoints, import must fail clearly rather than exposing MinIO internals.
- The metadata mapping from MDDash experiment data to VRE Lite metadata should be conservative. Fields that cannot be mapped confidently should be left for the user to review or fill in VRE Lite.
