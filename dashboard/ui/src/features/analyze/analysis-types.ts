import type { StatisticalData } from "@/api/generated/models"

export type { StatisticalData }

/**
 * The guarded input every renderer entry in `renderers/index.tsx` matches
 * against. Fetched results arrive as generated `AnalysisResult` and are passed
 * here as `unknown` — the guards, not the types, decide the payload family.
 */
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
