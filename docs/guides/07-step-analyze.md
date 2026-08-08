# Wizard Step 4: Analyze

The Analyze step works with a finished (or still-running) simulation. It has three parts: a compact **notebook controller** (for interactive analysis in JupyterLab), a **"Trajectory Viewer"** tab with a 3D Mol* viewer, and an **"Analysis"** tab with one-click built-in analyses.

Requirements: the selected simulation must be valid and point to an existing trajectory file and reference structure, and a simulation job must exist (the step unlocks while the job is still running, so partial trajectories can be inspected early).

## Notebook controller (analysis mode)

Same controller as in the Setup step, but the **Open** button deep-links into the experiment's **analysis.ipynb** in JupyterLab. Start it with a size tier and (optionally) a GPU for interactive, custom analysis with GROMACS/AmberTools available in the notebook environment.

## Trajectory Viewer tab

An interactive **Mol\*** 3D viewer loading the simulation's reference structure and trajectory (PDB/GRO structures, XTC/TRR trajectories, PRMTOP topologies are all understood). A **Reload** button re-mounts the viewer if a load appears stale or incomplete (e.g. the trajectory was still being written). If required files are missing, a dashed placeholder explains why (e.g. "Select a simulation above to view its structure.").

## Analysis tab

One-click analyses run as cluster jobs (not in the browser). The control row contains:

- **Analysis** dropdown — all available analysis types; entries with existing results carry a **"ready"** chip.
- **Preprocessing** dropdown — "Use Files As-Is" (default), "Image Only" (center the solute in the box), "Image and Fit" (image + remove rotation/translation). **AMBER experiments only offer "Use Files As-Is"**; imaging options require a GROMACS `.tpr` topology.
- **Calculate** button — starts the analysis job (reads **Re-calculate** when results already exist; shows "Running..." with a spinner while active). Disabled without a valid simulation/selection or while another analysis job runs — **only one analysis job at a time per simulation**.
- **Variant dropdown** — appears for analyses producing multiple result sets (numbered variants such as clusters or interactions; auto-selects the first).

While a job runs, its status chip and a "View logs"/"Hide logs" toggle appear, plus an ✕ cancel button (confirm "Stop the current analysis job? This run will be terminated and any partial output may be incomplete."). A failed run shows an ERROR chip and *"Previous analysis run failed. Inspect the logs to understand the failure before retrying."*

Result-area messages users may see: "No results yet. Select a simulation and click 'Calculate' to run this analysis."; "Analysis produced no data. This analysis may not apply to your system (e.g., no lipid membrane detected)."; "Select a simulation in the sidebar to run this analysis."; "The selected simulation is invalid. Repair it in the setup step."

## Available analyses

Membrane-specific analyses are auto-detected — if no lipid bilayer is present they produce no data rather than an error. All analyses are available for both engines unless noted.

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
| **Interactions** | interaction interfaces: residues highlighted per interface with coverage heatmap |
| **Density Profile** *(membrane)* | number/mass/charge/electron density along the membrane normal per component |
| **Thickness** *(membrane)* | leaflet separation over time, midplane drift, stability snapshot |
| **Area Per Lipid** *(membrane)* | median ± std area per lipid + per-leaflet area grid heatmaps |
| **Lipid Order** *(membrane)* | lipid order parameters along the acyl chain per lipid/residue |
| **Lipid Interactions** *(membrane)* | residue × lipid occupancy heatmap, top interacting residues and lipid species |
| **Energies** *(needs topology)* | per-residue electrostatic/van der Waals interaction energies, stacked contribution chart, top contributors |

## Gotchas

- Results persist; clicking Calculate again on a "ready" analysis re-runs and overwrites them.
- Deleting an analysis job also deletes its results.
- Analysis jobs are cluster jobs with their own CPU/memory allocation — like other jobs they survive browser restarts.
- Cluster lists are capped at the top 20 clusters.
- File listings and visibility can lag a few seconds behind Jupyter (storage sync cadence) — use Reload or retry if a brand-new trajectory doesn't load immediately.
