/**
 * Analysis data types for MD analysis visualization.
 * Copied from invenio-app's mdpositTypes.ts (analysis-related types only).
 */

import type { JobStatus } from "./types"

// ============================================================================
// Backend API Types
// ============================================================================

/** mwf analysis task names (mirrors Python AnalysisType enum) */
export const AnalysisType = {
  APL: "apl",
  CLUSTERS: "clusters",
  DENSITY: "density",
  DIST: "dist",
  ENERGIES: "energies",
  HBONDS: "hbonds",
  INTER: "inter",
  LINTER: "linter",
  LORDER: "lorder",
  PAIRWISE: "pairwise",
  PCA: "pca",
  PERRES: "perres",
  POCKETS: "pockets",
  RGYR: "rgyr",
  RMSDS: "rmsds",
  RMSF: "rmsf",
  SAS: "sas",
  THICKNESS: "thickness",
  TMSCORE: "tmscore",
} as const

export type AnalysisType = (typeof AnalysisType)[keyof typeof AnalysisType]

export const AnalysisPreprocessingMode = {
  AS_IS: "as_is",
  IMAGE: "image",
  IMAGE_FIT: "image_fit",
} as const

export type AnalysisPreprocessingMode = (typeof AnalysisPreprocessingMode)[keyof typeof AnalysisPreprocessingMode]

export interface AnalysisJob {
  id: string
  experiment_id: string
  created_at: string
  status: JobStatus
  analysis_name: AnalysisType
  structure_file: string
  trajectory_file: string
  results: string[]
}

export interface AnalysisInfo {
  value: AnalysisType
  label: string
  /** mwf output file name (after underscore→hyphen normalization). Differs from value when mwf uses different names for task vs output. */
  resultName: string
  requiresTopology?: boolean
  /** True when mwf produces both a summary file and numbered variants (base-00, base-01, …). */
  hasVariants?: boolean
}

export const AVAILABLE_ANALYSES: AnalysisInfo[] = [
  // Standard — work with structure + trajectory alone
  { value: AnalysisType.RMSDS, label: "RMSD", resultName: "rmsds" },
  { value: AnalysisType.RGYR, label: "Radius of Gyration", resultName: "rgyr" },
  { value: AnalysisType.RMSF, label: "RMSF (Fluctuation)", resultName: "fluctuation" },
  { value: AnalysisType.PCA, label: "PCA", resultName: "pca" },
  { value: AnalysisType.CLUSTERS, label: "Clusters", resultName: "clusters", hasVariants: true },
  { value: AnalysisType.PAIRWISE, label: "Pairwise RMSD", resultName: "rmsd-pairwise", hasVariants: true },
  { value: AnalysisType.PERRES, label: "Per-Residue RMSD", resultName: "rmsd-perres" },
  { value: AnalysisType.HBONDS, label: "Hydrogen Bonds", resultName: "hbonds", hasVariants: true },
  { value: AnalysisType.SAS, label: "SASA", resultName: "sasa" },
  { value: AnalysisType.POCKETS, label: "Pockets", resultName: "pockets" },
  { value: AnalysisType.TMSCORE, label: "TM-Scores", resultName: "tmscores" },
  { value: AnalysisType.DIST, label: "Distance Per Residue", resultName: "dist-perres", hasVariants: true },
  { value: AnalysisType.INTER, label: "Interactions", resultName: "interactions" },
  // Membrane — auto-detected from structure; skipped if no lipid bilayer present
  { value: AnalysisType.DENSITY, label: "Density Profile", resultName: "density" },
  { value: AnalysisType.THICKNESS, label: "Thickness", resultName: "thickness" },
  { value: AnalysisType.APL, label: "Area Per Lipid", resultName: "apl" },
  { value: AnalysisType.LORDER, label: "Lipid Order", resultName: "lipid-order" },
  { value: AnalysisType.LINTER, label: "Lipid Interactions", resultName: "lipid-inter" },
  { value: AnalysisType.ENERGIES, label: "Energies", resultName: "energies", requiresTopology: true },
]

// ============================================================================
// Analysis Data Types (from mddb-workflow JSON output)
// ============================================================================

export interface StatisticalData {
  average: number
  stddev: number
  min: number
  max: number
  data: number[]
}

export interface RMSDAnalysis {
  step: number
  y: {
    rmsd: StatisticalData
  }
}

export interface DistancePerResidueAnalysis {
  data: {
    name: string
    means: number[][]
    stdvs: number[][]
  }[]
}

export interface EnergiesAgentData {
  labels: string[]
  es: number[]
  ies: number[]
  fes: number[]
  vdw: number[]
  ivdw: number[]
  fvdw: number[]
  both: number[]
  iboth: number[]
  fboth: number[]
}

export interface EnergiesAnalysis {
  data: {
    name: string
    agent1: EnergiesAgentData
    agent2: EnergiesAgentData
  }[]
}

export interface FluctuationAnalysis {
  start: number
  step: number
  y: {
    rmsf: StatisticalData
  }
}

export interface HydrogenBondsAnalysis {
  data: {
    name: string
    acceptors: number[]
    donors: number[]
    hydrogens: number[]
    hbonds: boolean[][]
  }[]
}

export interface PCAAnalysis {
  framestep: number
  atoms: number[]
  eigenvalues: number[]
  projections: number[][]
}

export interface PocketsAnalysis {
  data: {
    name: string
    volumes: number[]
    atoms: number[]
  }[]
}

export interface MembraneMapAnalysis {
  n_mems: number
  mems: Record<
    string,
    {
      leaflets: {
        bot: number[]
        top: number[]
      }
      polar_atoms: {
        bot: number[]
        top: number[]
      }
    }
  >
  no_mem_lipid: number[]
}

export interface AreaPerLipidAnalysis {
  data: {
    "lower leaflet": number[][]
    "upper leaflet": number[][]
    grid_x: number[]
    grid_y: number[]
    median: number
    std: number
  }
}

export interface DensityProfileComponent {
  name: string
  selection: number[]
  number: { dens: number[]; stdv: number[] }
  mass: { dens: number[]; stdv: number[] }
  charge: { dens: number[]; stdv: number[] }
  electron: { dens: number[]; stdv: number[] }
}

export interface DensityProfileAnalysis {
  data: {
    comps: DensityProfileComponent[]
    z: number[]
  }
}

export interface LipidInteractionAnalysis {
  data: {
    residue_indices: number[]
    [lipidInchiKey: string]: number[]
  }
}

export interface LipidOrderSegment {
  atoms: string[]
  avg: number[]
  std: number[]
}

export interface LipidOrderAnalysis {
  data: Record<string, Record<string, LipidOrderSegment>>
}

export interface ThicknessAnalysis {
  step?: number
  data: {
    frame: number[]
    mean_positive: number[]
    mean_negative: number[]
    std_positive: number[]
    std_negative: number[]
    thickness: number[]
    std_thickness: number[]
    midplane_z: number[]
  }
}

export interface RadiusOfGyrationAnalysis {
  start: number
  step: number
  y: {
    rgyr: StatisticalData
    rgyrx: StatisticalData
    rgyry: StatisticalData
    rgyrz: StatisticalData
  }
}

export interface RMSDPairwiseMatrix {
  name: string
  rmsds: number[][]
}

export interface RMSDPairwiseAnalysis {
  start: number
  step: number
  data: RMSDPairwiseMatrix[]
}

export interface RMSDPerResidueSeries {
  name: string
  rmsds: number[]
}

export interface RMSDPerResidueAnalysis {
  step?: number
  data: RMSDPerResidueSeries[]
}

export interface RMSDPerResidueMatrixAnalysis {
  step?: number
  rmsdpr: number[][]
}

export interface RMSDsAnalysis {
  start: number
  step: number
  data: {
    reference: string
    group: string
    values: number[]
  }[]
}

export interface SolventAccessibleSurfaceAnalysis {
  step?: number
  saspf: Array<Array<number | null>>
  means?: number[]
  stdvs?: number[]
}

export interface TMScoresAnalysis {
  start: number
  step: number
  data: {
    reference: string
    group: string
    values: number[]
  }[]
}

export interface ClustersAnalysis {
  name: string
  cutoff: number
  clusters: {
    frames: number[]
    main: number
  }[]
  transitions: {
    from: number
    to: number
    count: number
  }[]
  step: number
  version: string
}

export interface InteractionData {
  name: string
  agent_1: string
  agent_2: string
  has_cg?: boolean
  version?: string
  strong_bonds?: number[][]
  atom_indices_1?: number[]
  atom_indices_2?: number[]
  interface_atom_indices_1?: number[]
  interface_atom_indices_2?: number[]
  residue_indices_1?: number[]
  residue_indices_2?: number[]
  interface_indices_1?: number[]
  interface_indices_2?: number[]
}

export type Analysis =
  | MembraneMapAnalysis
  | AreaPerLipidAnalysis
  | DensityProfileAnalysis
  | LipidInteractionAnalysis
  | LipidOrderAnalysis
  | ThicknessAnalysis
  | DistancePerResidueAnalysis
  | EnergiesAnalysis
  | FluctuationAnalysis
  | HydrogenBondsAnalysis
  | InteractionData
  | PCAAnalysis
  | PocketsAnalysis
  | RMSDAnalysis
  | RadiusOfGyrationAnalysis
  | RMSDPairwiseAnalysis
  | RMSDPerResidueAnalysis
  | RMSDPerResidueMatrixAnalysis
  | RMSDsAnalysis
  | SolventAccessibleSurfaceAnalysis
  | TMScoresAnalysis
  | ClustersAnalysis
