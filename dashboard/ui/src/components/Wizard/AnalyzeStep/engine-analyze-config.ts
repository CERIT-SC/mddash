import type { Engine } from "@/util/const"

interface AnalyzeConfig {
  structureExts: string[]
  trajectoryExts: string[]
  topologyExts: string[]
  preprocessingTopologyExts: string[]
}

export const ANALYZE_CONFIG: Record<Engine, AnalyzeConfig> = {
  gmx: {
    structureExts: ["pdb", "gro"],
    trajectoryExts: ["xtc", "trr"],
    topologyExts: ["tpr", "top", "prmtop", "psf"],
    preprocessingTopologyExts: ["tpr"],
  },
  amber: {
    structureExts: ["pdb"],
    trajectoryExts: ["nc"],
    topologyExts: ["prmtop", "parm7"],
    preprocessingTopologyExts: [],
  },
}
