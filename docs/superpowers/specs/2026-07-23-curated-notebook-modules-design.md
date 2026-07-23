# Curated Notebook Modules Design

## Summary

MDDash will present curated notebook modules from the configured default
notebooks repository. Users choose an MD engine and then choose a compatible
module, such as the GROMACS protein workflow. MDDash checks out only that
module's directory and copies its contents into the experiment root.

The repository URL is not displayed in the normal creation flow. Users can
choose a secondary custom-repository flow when they need their own Git or
Binder-compatible repository. Custom repositories retain the current behavior:
MDDash clones the complete default branch and copies the repository root into
the experiment.

## Goals

- Show curated notebook workflows as product modules rather than Git paths.
- Filter modules by the experiment's selected MD engine.
- Copy only the selected curated module into a new experiment.
- Keep each curated module self-contained in the notebooks repository.
- Preserve full support for arbitrary custom repositories.
- Keep the default creation flow free of repository configuration fields.
- Leave room for additional protein, membrane, ligand, and other workflows.

## Non-Goals

- Discovering modules from arbitrary repositories.
- Requiring custom repositories to follow the curated directory layout.
- Selective checkout of custom repositories.
- User-selectable Git branches, tags, or commits.
- A dedicated Binder catalog or Binder-specific creation flow.
- Runtime operator overrides of the curated module catalog.
- Updating notebook content after experiment creation.

Custom repositories may continue to contain Binder configuration. The existing
notebook startup behavior remains responsible for using it.

## Current State

Experiment creation currently accepts an always-visible notebooks repository
URL. The API shallow-clones the remote default branch, removes `.git`, and moves
all repository-root content into the experiment directory. The selected engine
does not affect the clone.

The current `mddash-notebooks` default branch contains seven root-level files:

```text
amber-protein-setup.ipynb
amber.schema.json
amber_wrapper.py
gromacs.schema.json
mdanalysis_utils.py
protein-analysis.ipynb
protein-setup.ipynb
```

The files form two self-contained groups:

- GROMACS protein: `protein-setup.ipynb`, `protein-analysis.ipynb`,
  `mdanalysis_utils.py`, and `gromacs.schema.json`.
- AMBER protein: `amber-protein-setup.ipynb`, `amber_wrapper.py`, and
  `amber.schema.json`.

The repository has no Binder configuration. Both setup notebooks expect
`input.pdb` and write their simulation manifest and generated directories
relative to the experiment root.

## Curated Repository Layout

The initial repository organization is:

```text
gromacs/
  protein/
    protein-setup.ipynb
    protein-analysis.ipynb
    mdanalysis_utils.py
    gromacs.schema.json

amber/
  protein/
    amber-protein-setup.ipynb
    amber_wrapper.py
    amber.schema.json
```

Future modules use the same engine/module shape, for example
`gromacs/membrane/` or `amber/protein-ligand/`. The shape is a first-party
organization convention, not a discovery contract for custom repositories.

Each module must be self-contained. Notebooks, local Python helpers, schemas,
and optional environment or Binder files required by that workflow live inside
the module directory. MDDash copies the directory's contents, not the directory
itself, into the experiment root. This preserves the current assumptions about
`input.pdb`, local imports, schema paths, and generated simulation files.

## Module Catalog

MDDash owns a versioned `notebook-modules.json` file bundled with the Dashboard
API image. It is product content and is not part of runtime deployment
configuration. The existing `defaultNotebooksRepo` setting remains the only
operator-configurable part of the curated source.

The initial catalog is equivalent to:

```json
{
  "schema_version": 1,
  "modules": [
    {
      "id": "gromacs-protein",
      "name": "Protein",
      "description": "Prepare and analyze a solvated protein with GROMACS.",
      "engine": "GMX",
      "path": "gromacs/protein"
    },
    {
      "id": "amber-protein",
      "name": "Protein",
      "description": "Prepare a solvated protein with AMBER.",
      "engine": "AMBER",
      "path": "amber/protein"
    }
  ]
}
```

A JSON Schema stored in the MDDash repository validates the JSON catalog in CI
and when the API starts. Validation requires a supported schema version, unique
module IDs, non-empty display fields, a known engine, and a safe relative path.
Paths may not be absolute or contain `..`, empty components, backslashes, or
control characters. Invalid bundled product configuration is a startup error,
not a recoverable user error.

The API is the catalog's single source of truth. A read-only endpoint returns
the display metadata required by the UI. It need not return repository URLs or
paths. Experiment creation accepts a module ID, and the API resolves that ID to
the server-side engine and path. It rejects a module whose engine differs from
the submitted experiment engine.

Changing `defaultNotebooksRepo` is supported, but the replacement repository
must implement the paths in the bundled catalog. Installations needing a
different curated catalog can introduce a runtime override in a future design;
arbitrary user repositories use the custom flow instead.

## Creation UX

The normal creation form has this order:

1. Experiment name.
2. MD engine selection.
3. Initial data selection and fields.
4. Notebook module selection.
5. Create experiment.

The module section fetches the bundled catalog through the API and shows only
modules compatible with the selected engine. Modules are presented by name and
description; internal Git paths are not shown. A module selection is required,
including when only one compatible module currently exists. Changing engines
clears an incompatible selection and displays the new engine's modules.

The repository input is absent from this default view. A secondary **Use custom
notebooks repository** action switches the module section into custom mode and
reveals the current repository URL and optional access-token controls. Custom
mode retains the explicit engine selected above. It does not show module or
subdirectory selection.

Switching back to curated modules clears the custom URL and token from form
state. Tokens remain transient and are never persisted.

Loading the module catalog is independent of Git access and requires no
repository probe. If catalog loading fails, creation is disabled and the UI
offers a retry. Custom repository creation remains available.

## API And Clone Behavior

Curated creation submits the selected module ID instead of a notebooks
repository URL. The API:

1. Loads the validated catalog entry.
2. Verifies that its engine matches the experiment engine.
3. Uses the configured `defaultNotebooksRepo` and its remote default branch.
4. Performs a shallow partial clone in a temporary directory.
5. Sparse-checks out the catalog entry's path.
6. Verifies that the path exists and is a directory in the checked-out commit.
7. Copies that directory's contents into the experiment root.
8. Removes temporary Git data.
9. Continues the existing PDB, uploaded-file, or repository-record import.

The default Git host is expected to support partial clone, allowing unselected
file blobs to remain undownloaded. If the host ignores or does not support blob
filtering, creation may download additional Git objects, but MDDash still copies
only the selected module into the experiment.

Custom creation keeps the existing API and clone semantics: shallow-clone the
remote default branch, remove `.git`, and copy the complete repository root into
the experiment. No directory convention, catalog, or sparse checkout is applied
to custom repositories.

The initial implementation does not add database columns. The existing
`notebooks_repo` value stores the configured default repository for curated
experiments and the submitted URL for custom experiments. The selected module
is creation input used to construct the workspace; the copied workspace remains
the experiment's executable notebook source.

## Errors And Cleanup

Curated creation reports distinct errors for:

- unknown or engine-incompatible module ID;
- unreachable configured repository;
- clone timeout or Git failure;
- selected module path missing from the repository; and
- failure while copying module content.

Errors must not include authenticated URLs or tokens. Existing experiment
directory cleanup remains in effect when preparation fails.

Custom repository validation, authentication, timeout, and cleanup behavior
remain unchanged by this feature.

## Rollout

The catalog and notebooks repository live in separate repositories and no Git
ref is pinned. Use an overlap rollout to prevent either application version from
observing an incompatible layout:

1. Add `gromacs/protein/` and `amber/protein/` to `mddash-notebooks` while
   temporarily retaining the current root-level files.
2. Deploy the MDDash release that provides module selection and selective
   checkout.
3. After supported MDDash deployments use the new flow, remove the duplicate
   root-level notebook files from `mddash-notebooks`.

An older MDDash version continues to find root notebooks during step 2. The new
version finds the module directories from step 1. This avoids requiring branch
or tag configuration solely for migration coordination.

## Testing

### Catalog

- Validate the bundled catalog against its JSON Schema.
- Reject duplicate IDs, unsupported engines, unknown schema versions, and
  unsafe paths.
- Verify the catalog endpoint returns stable display metadata without internal
  paths or repository credentials.

### API And Git

- Create each curated protein module and verify that only its files appear in
  the experiment root.
- Reject unknown and engine-incompatible module IDs.
- Report a missing configured module path and remove the partial experiment.
- Verify shallow partial-clone arguments and the fallback behavior of a server
  without blob filtering.
- Verify custom repositories still copy their complete root, including root
  Binder files.
- Verify private custom repository tokens remain transient and redacted.
- Exercise PDB, uploaded-file, and repository-record initialization with a
  curated module.

### UI

- Hide the repository field in curated mode.
- Filter module cards when the engine changes and clear incompatible choices.
- Require a module selection before curated creation.
- Submit module ID and engine without trusting a client-provided path.
- Switch between curated and custom modes and clear custom credentials when
  leaving custom mode.
- Preserve existing custom URL validation, token controls, and pending state.
- Display catalog-load and creation errors with retry behavior.

### Repository Migration

- Verify each reorganized module contains every notebook, helper, and schema it
  needs when copied alone into an empty experiment directory.
- Smoke-test GROMACS and AMBER protein setup from `input.pdb` after selective
  checkout.

## Future Extensions

- Add membrane, ligand, nucleic-acid, and other curated modules by extending the
  bundled catalog and default repository together.
- Add dedicated Binder repository discovery or presentation if custom Binder
  usage requires more guidance than the existing Git flow.
- Add configurable catalogs if installations demonstrate a need for their own
  curated product modules.
- Record resolved Git commits or support explicit refs if notebook provenance
  and reproducible re-import become requirements.
