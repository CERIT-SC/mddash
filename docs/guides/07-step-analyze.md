# Wizard Step 4: Analyze

The Analyze step works with a running or finished simulation. It is titled **"Analyze the results"** (*"Each model is a snapshot of your molecule during the simulation. Step through them to see how the structure moved over time, or drag inside the viewer to rotate and zoom."*) and has two tabs — **"View Trajectories"** (default) and **"Analyze"** — plus a **notebook launcher** sitting in the same row after an "or" separator. While the production run is still going, a banner reads **"Simulation is still running (20%)"** — *"Trajectories and analyses will change as more results are calculated."*

Requirements: the selected simulation must be valid and point to an existing trajectory file and reference structure. The step unlocks once the production run is RUNNING or FINISHED, so partial trajectories can be inspected early. When the manifest is unusable, placeholders explain why: "The selected simulation is invalid. Repair it in the setup step." or "Missing required files: reference_structure, trajectory."

## Notebook launcher

A compact inline control (pill labelled **"Notebook"**): pick a **Size** tier (options shown as resources, e.g. `5 cores / 8 GB`), optionally tick **GPU**, and click **"Start notebook"** ("Starting…" while pending). Once the notebook is up, the launcher switches to a live readout — **"Starting…"**, **"Initializing…"**, "Taking longer than expected" after repeated startup-probe failures, then a ticking **uptime** — with **"Open notebook"** (deep-links into the experiment's **analysis.ipynb** in JupyterLab, new tab) and **"Stop notebook"**. While the notebook is running, a **notebook status bar** with the same controls also appears under the site header on every experiment page. Starting when the per-user notebook limit is reached opens the **"Notebook limit reached"** dialog (see "Getting Started").

## View Trajectories tab

An interactive **Mol\*** 3D viewer loading the simulation's reference structure and trajectory. Understood formats include PDB/GRO/mmCIF/PSF/PRMTOP structures & topologies and XTC/TRR/DCD/NetCDF/LAMMPS trajectories. A **"Reload Models"** button re-mounts the viewer if a load appears stale or incomplete (e.g. the trajectory was still being written). If required files are missing, a dashed placeholder explains why; the fallback reads "Select a simulation above to view its structure." Load failures show **"The structure could not be loaded"** with the error detail (including structure/trajectory atom-set mismatches).

## Analyze tab

One-click analyses run as cluster jobs (not in the browser). The control row contains:

- **Analysis** dropdown (placeholder "Select analysis...") — all available analysis types; entries with existing results carry a **"ready"** chip.
- **Preprocessing** dropdown (placeholder "Select preprocessing...") — "Use Files As-Is" (default), "Image Only", "Image and Fit". A tooltip explains: *"How the trajectory is treated before analysis: image re-centers molecules in the simulation box; image and fit also aligns them to the reference structure."* **AMBER experiments only offer "Use Files As-Is"**; imaging options require a GROMACS `.tpr` topology.
- **Calculate** button — starts the analysis job ("Analysis job submitted" toast; reads **Re-calculate** when results already exist). Disabled without a usable simulation/selection or while another analysis job runs — **only one analysis job at a time per simulation** (submitting a new one deletes the simulation's previous analysis jobs).

While a job runs, the buttons are replaced by a status chip — a spinner with **"Calculating \<analysis name\>"** (e.g. "Calculating RMSD") — plus a **"Stop calculation"** button (confirm dialog **"Cancel analysis job"**: *"Stop the current analysis job? This run will be terminated and any partial output may be incomplete."* with **"Keep running"** / **"Cancel job"**). A **"View logs"** / **"Hide logs"** toggle streams the job log (hidden while the job is only starting). If a finished analysis ran on a partial trajectory, a **"Calculated at X%"** warning badge marks the result until the trajectory completes.

A failed run shows a durable error alert — **"Previous analysis run failed."** / *"Inspect the logs to understand the failure before retrying."* — with its own View-logs toggle.

Result-area states users may see: "Select an analysis to view or calculate."; "Results are being calculated…"; "Loading analysis data…"; "No results yet." with the hint "Choose an analysis and click Calculate to run it."; "Analysis produced no data." with the hint "This analysis may not apply to your system (e.g., no lipid membrane detected)."

- **Variant dropdown** — appears above the results for analyses producing multiple numbered result sets (Clusters, Pairwise RMSD, Hydrogen Bonds, Distance Per Residue, Energies); it auto-selects the first variant.

## Available analyses

Membrane-specific analyses are auto-detected — if no lipid bilayer is present they produce no data rather than an error. All analyses are available for both engines unless noted. Charts follow the design system palette in light and dark mode.

| Analysis | What it shows |
|---|---|
| **RMSD** | line chart of RMSD (nm) over frames per reference group, with a reference picker |
| **Radius of Gyration** | Rg (nm) over frames including x/y/z components |
| **RMSF (Fluctuation)** | per-residue fluctuation: RMSF (nm) vs residue index |
| **PCA** | principal component analysis: scree plot ("explained variance") + 2D scatter of trajectory projections with selectable PC axes |
| **Clusters** | RMSD-based conformational clustering: stats (count, frames, cutoff), bar chart of top-20 cluster populations, transition-count heatmap, most frequent transitions |
| **Pairwise RMSD** | all-against-all RMSD heatmap across frame ranges |
| **Hydrogen Bonds** | H-bond persistence per interaction, bonds-formed-per-frame timeline, occupancy heatmap |
| **SASA** | solvent-accessible surface area over time + per-residue exposure ranking |
| **Pockets** | pocket volume over time (Å³) per pocket + top pockets by average volume |
| **TM-Scores** | TM-score vs frame per reference group |
| **Distance Per Residue** | per-residue distance statistics (mean/variability) for an interaction + heatmap |
| **RMSD Per Residue** | per-residue RMSD (nm) vs frame, with a residue picker and summary stats |
| **Interactions** | interaction interfaces: residues highlighted per interface with coverage heatmap |
| **Density Profile** *(membrane)* | number/mass/charge/electron density along the membrane normal per component |
| **Thickness** *(membrane)* | leaflet separation over time, midplane drift, stability snapshot |
| **Area Per Lipid** *(membrane)* | median ± std area per lipid + per-leaflet area grid heatmaps |
| **Lipid Order** *(membrane)* | lipid order parameters along the acyl chain per lipid/residue |
| **Lipid Interactions** *(membrane)* | residue × lipid occupancy heatmap, top interacting residues and lipid species |
| **Energies** *(needs topology)* | per-residue electrostatic/van der Waals interaction energies, stacked contribution chart, top contributors |

## Gotchas

- Results persist; clicking Re-calculate on a "ready" analysis re-runs and overwrites them.
- Stopping/cancelling an analysis job keeps its completed results — only temporary files are removed. A *new* submission for the same simulation deletes the previous analysis jobs.
- Analysis jobs are cluster jobs with their own CPU/memory allocation — like other jobs they survive browser restarts.
- Cluster lists are capped at the top 20 clusters ("Showing top 20" badge).
- File listings and visibility can lag a few seconds behind Jupyter (storage sync cadence) — use **Reload Models** or retry if a brand-new trajectory doesn't load immediately.
