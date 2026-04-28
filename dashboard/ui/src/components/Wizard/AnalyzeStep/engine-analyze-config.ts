import type { Engine } from "@/util/const"

interface AnalyzeConfig {
  structureExts: string[]
  trajectoryExts: string[]
  topologyExts: string[]
  preprocessingTopologyExts: string[]
  trajectoryRequiresTopology: boolean
}

export const ANALYZE_CONFIG: Record<Engine, AnalyzeConfig> = {
  GMX: {
    structureExts: ["pdb", "gro"],
    trajectoryExts: ["xtc", "trr"],
    topologyExts: ["tpr", "top"],
    preprocessingTopologyExts: ["tpr"],
    trajectoryRequiresTopology: false,
  },
  AMBER: {
    structureExts: ["pdb"],
    trajectoryExts: ["nc"],
    topologyExts: ["prmtop", "parm7"],
    preprocessingTopologyExts: [],
    trajectoryRequiresTopology: true,
  },
}
