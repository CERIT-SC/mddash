import type { FC, ReactElement } from "react"

import { BarChart3 } from "lucide-react"

import type { Analysis } from "@/util/analysis-types"

import AreaPerLipidPanel from "./AreaPerLipidPanel"
import ClustersPanel from "./ClustersPanel"
import DensityProfilePanel from "./DensityProfilePanel"
import DistancePerResiduePanel from "./DistancePerResiduePanel"
import EnergiesPanel from "./EnergiesPanel"
import FluctuationChart from "./FluctuationChart"
import HydrogenBondsAnalysisPanel from "./HydrogenBondsAnalysisPanel"
import InteractionsAnalysisPanel from "./InteractionsAnalysisPanel"
import LipidInteractionsPanel from "./LipidInteractionsPanel"
import LipidOrderPanel from "./LipidOrderPanel"
import MembraneMapAnalysisPanel from "./MembraneMapAnalysisPanel"
import PcaAnalysisPanel from "./PcaAnalysisPanel"
import PocketsAnalysisPanel from "./PocketsAnalysisPanel"
import RgChart from "./RgChart"
import RMSDChart from "./RMSDChart"
import RMSDPairwiseHeatmap from "./RMSDPairwiseHeatmap"
import RMSDPairwiseInterfacePanel from "./RMSDPairwiseInterfacePanel"
import RMSDPerResidueChart from "./RMSDPerResidueChart"
import RMSDsChart from "./RMSDsChart"
import SasaAnalysisPanel from "./SasaAnalysisPanel"
import ThicknessAnalysisPanel from "./ThicknessAnalysisPanel"
import TMScoresChart from "./TMScoresChart"
import {
  extractDistancePerResidueAnalysis,
  extractEnergiesAnalysis,
  extractHydrogenBondsAnalysis,
  extractPcaAnalysis,
  extractRmsdPairwiseAnalysis,
  extractRmsdPerResidueAnalysis,
  isAreaPerLipidAnalysis,
  isClustersAnalysis,
  isDensityProfileAnalysis,
  isFluctuationAnalysis,
  isInteractionsAnalysis,
  isLipidInteractionAnalysis,
  isLipidOrderAnalysis,
  isMembraneMapAnalysis,
  isPocketsAnalysis,
  isRadiusOfGyrationAnalysis,
  isRmsdAnalysis,
  isRmsdsAnalysis,
  isSasaAnalysis,
  isThicknessAnalysis,
  isTMScoresAnalysis,
} from "./utils"

const ANALYSES = {
  MEM_MAP: "mem-map",
  APL: "apl",
  CLUSTERS: "clusters",
  DENSITY: "density",
  DIST_PERRES: "dist-perres",
  ENERGIES: "energies",
  HBONDS: "hbonds",
  INTERACTIONS: "interactions",
  LIPID_INTER: "lipid-inter",
  LIPID_ORDER: "lipid-order",
  RMSD_PAIRWISE: "rmsd-pairwise",
  RMSD_PAIRWISE_INTERFACE: "rmsd-pairwise-interface",
  PCA: "pca",
  POCKETS: "pockets",
  RMSD_PERRES: "rmsd-perres",
  RGYR: "rgyr",
  RMSDS: "rmsds",
  FLUCTUATION: "fluctuation",
  SASA: "sasa",
  THICKNESS: "thickness",
  TMSCORES: "tmscores",
  RMSD: "rmsd",
} as const

const stripNumericVariantSuffix = (name: string) => name.replace(/-\d+$/, "")

const matchesAnalysisName = (name: string, targets: string | string[]) => {
  const normalized = stripNumericVariantSuffix(name)
  const targetList = Array.isArray(targets) ? targets : [targets]
  return targetList.some((target) => normalized === target)
}

const DIST_PERRES_VARIANTS = [ANALYSES.DIST_PERRES, `${ANALYSES.DIST_PERRES}-mean`, `${ANALYSES.DIST_PERRES}-stdv`]

type AnalysisRendererProps = {
  analysisName: string
  data: Analysis
}

const renderPlaceholder = (analysisName: string): ReactElement => (
  <div className="bg-muted border-muted-foreground/25 flex h-full flex-1 items-center justify-center rounded-lg border-2 border-dashed">
    <div className="space-y-2 text-center">
      <BarChart3 className="text-muted-foreground/50 mx-auto h-12 w-12" />
      <p className="text-muted-foreground text-sm">Visualization</p>
      <p className="text-muted-foreground/75 text-xs">
        Data loaded for <strong>{analysisName}</strong>, but no renderer is implemented yet.
      </p>
    </div>
  </div>
)

const AnalysisRenderer: FC<AnalysisRendererProps> = ({ analysisName, data }: AnalysisRendererProps) => {
  for (const render of analysisRenderers) {
    const result = render(analysisName, data)
    if (result) {
      return result
    }
  }

  // Fallback placeholder
  return renderPlaceholder(analysisName)
}

type Renderer = (analysisName: string, data: Analysis) => ReactElement | null

const analysisRenderers: Renderer[] = [
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.RMSDS) && isRmsdsAnalysis(data)) {
      return <RMSDsChart data={data} />
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.RMSD_PAIRWISE)) {
      const pairwiseData = extractRmsdPairwiseAnalysis(data)
      if (pairwiseData) {
        return <RMSDPairwiseHeatmap data={pairwiseData} />
      }
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.RMSD_PAIRWISE_INTERFACE)) {
      const pairwiseData = extractRmsdPairwiseAnalysis(data)
      if (pairwiseData) {
        return <RMSDPairwiseInterfacePanel data={pairwiseData} />
      }
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.RMSD) && isRmsdAnalysis(data)) {
      return <RMSDChart data={data} />
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.RGYR) && isRadiusOfGyrationAnalysis(data)) {
      return <RgChart data={data} />
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.FLUCTUATION) && isFluctuationAnalysis(data)) {
      return <FluctuationChart data={data} />
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.RMSD_PERRES)) {
      const perResidueData = extractRmsdPerResidueAnalysis(data)
      if (perResidueData) {
        return <RMSDPerResidueChart data={perResidueData} />
      }
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.TMSCORES) && isTMScoresAnalysis(data)) {
      return <TMScoresChart data={data} />
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.PCA)) {
      const pcaData = extractPcaAnalysis(data)
      if (pcaData) {
        return <PcaAnalysisPanel data={pcaData} />
      }
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.POCKETS) && isPocketsAnalysis(data)) {
      return <PocketsAnalysisPanel data={data} />
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.SASA) && isSasaAnalysis(data)) {
      return <SasaAnalysisPanel data={data} />
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.APL) && isAreaPerLipidAnalysis(data)) {
      return <AreaPerLipidPanel data={data} />
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.MEM_MAP) && isMembraneMapAnalysis(data)) {
      return <MembraneMapAnalysisPanel data={data} />
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.LIPID_INTER) && isLipidInteractionAnalysis(data)) {
      return <LipidInteractionsPanel data={data} />
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.THICKNESS) && isThicknessAnalysis(data)) {
      return <ThicknessAnalysisPanel data={data} />
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.DENSITY) && isDensityProfileAnalysis(data)) {
      return <DensityProfilePanel data={data} />
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, DIST_PERRES_VARIANTS)) {
      const distPerResData = extractDistancePerResidueAnalysis(data)
      if (distPerResData) {
        return <DistancePerResiduePanel data={distPerResData} />
      }
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.LIPID_ORDER) && isLipidOrderAnalysis(data)) {
      return <LipidOrderPanel data={data} />
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.HBONDS)) {
      const hbondsData = extractHydrogenBondsAnalysis(data)
      if (hbondsData) {
        return <HydrogenBondsAnalysisPanel data={hbondsData} />
      }
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.INTERACTIONS) && isInteractionsAnalysis(data)) {
      return <InteractionsAnalysisPanel data={data} />
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.ENERGIES)) {
      const energiesData = extractEnergiesAnalysis(data)
      if (energiesData) {
        return <EnergiesPanel data={energiesData} />
      }
    }
    return null
  },
  (analysisName, data) => {
    if (matchesAnalysisName(analysisName, ANALYSES.CLUSTERS) && isClustersAnalysis(data)) {
      return <ClustersPanel data={data} />
    }
    return null
  },
]

export default AnalysisRenderer
