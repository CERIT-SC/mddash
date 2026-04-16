import { useEffect, useMemo, useState } from "react"

import { RefreshCw } from "lucide-react"
import { type BuiltInCoordinatesFormat } from "molstar/lib/mol-plugin-state/formats/coordinates"
import { type BuiltInTrajectoryFormat } from "molstar/lib/mol-plugin-state/formats/trajectory"

import {
  AnalysisPreprocessingMode,
  AVAILABLE_ANALYSES,
  type AnalysisPreprocessingMode as AnalysisPreprocessingModeValue,
  type AnalysisType,
} from "@/util/analysis-types"
import type { FileOption } from "@/util/types"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import MolStar from "@/components/MolStar"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import AnalysisPanel from "./AnalysisPanel"
import AnalyzeSidebar from "./AnalyzeSidebar"
import { ANALYZE_CONFIG } from "./engine-analyze-config"

const AnalyzeStep = (props: WizardStepProps) => {
  const { experiment } = props

  const engineConfig = ANALYZE_CONFIG[experiment.engine]

  const [structureFile, setStructureFile] = useState<FileOption | null>(null)
  const [coordsFile, setCoordsFile] = useState<FileOption | null>(null)
  const [topologyFile, setTopologyFile] = useState<FileOption | null>(null)
  const [selectedAnalysis, setSelectedAnalysis] = useState<AnalysisType | null>(null)
  const [preprocessingMode, setPreprocessingMode] = useState<AnalysisPreprocessingModeValue>(
    AnalysisPreprocessingMode.AS_IS
  )
  const [reloadKey, setReloadKey] = useState(0)
  const [activeTab, setActiveTab] = useState("viewer")

  useEffect(() => {
    if (!structureFile) setCoordsFile(null)
  }, [structureFile])

  const analysisConfig = useMemo(
    () => AVAILABLE_ANALYSES.find((analysis) => analysis.value === selectedAnalysis),
    [selectedAnalysis]
  )
  const topologyRequired = preprocessingMode !== AnalysisPreprocessingMode.AS_IS || !!analysisConfig?.requiresTopology
  const topologyFormats =
    preprocessingMode === AnalysisPreprocessingMode.AS_IS
      ? engineConfig.topologyExts
      : engineConfig.preprocessingTopologyExts
  const topologyTitle =
    preprocessingMode === AnalysisPreprocessingMode.AS_IS
      ? analysisConfig?.requiresTopology
        ? "Select topology file"
        : "Select topology file (optional)"
      : "Select simulation topology file"

  useEffect(() => {
    if (!topologyRequired) {
      if (topologyFile) setTopologyFile(null)
      return
    }

    if (!topologyFile) return

    const suffix = topologyFile.path.split(".").pop()?.toLowerCase() ?? ""
    const allowedSuffixes =
      preprocessingMode === AnalysisPreprocessingMode.AS_IS
        ? engineConfig.topologyExts
        : engineConfig.preprocessingTopologyExts

    if (!allowedSuffixes.includes(suffix)) {
      setTopologyFile(null)
    }
  }, [preprocessingMode, topologyFile, topologyRequired, engineConfig])

  const molstarViewer = useMemo(() => {
    if (!structureFile) return null
    return (
      <MolStar
        key={reloadKey}
        width="100%"
        height="600px"
        structureUrl={structureFile.url}
        structureFormat={structureFile.name.split(".").pop() as BuiltInTrajectoryFormat}
        coordsUrl={coordsFile?.url}
        coordsFormat={coordsFile ? (coordsFile.name.split(".").pop() as BuiltInCoordinatesFormat) : undefined}
      />
    )
  }, [structureFile, coordsFile, reloadKey])

  return (
    <div className="flex w-full flex-col items-center gap-4">
      <div className="flex w-[90%] flex-col gap-4 xl:flex-row">
        <AnalyzeSidebar
          experimentId={experiment.id}
          structureExts={engineConfig.structureExts}
          trajectoryExts={engineConfig.trajectoryExts}
          structureFile={structureFile}
          topologyRequired={topologyRequired}
          topologyFormats={topologyFormats}
          topologyTitle={topologyTitle}
          preprocessingMode={preprocessingMode}
          onStructureSelected={setStructureFile}
          onCoordsSelected={setCoordsFile}
          onTopologySelected={setTopologyFile}
        />

        <Tabs value={activeTab} onValueChange={setActiveTab} className="min-w-0 flex-1">
          <div className="flex items-center justify-between">
            <TabsList>
              <TabsTrigger value="viewer">Structure Viewer</TabsTrigger>
              <TabsTrigger value="analysis">Analysis</TabsTrigger>
            </TabsList>
            {coordsFile && activeTab === "viewer" && (
              <Button size="sm" variant="outline" onClick={() => setReloadKey((k) => k + 1)}>
                <RefreshCw className="mr-1 h-3.5 w-3.5" />
                Reload
              </Button>
            )}
          </div>

          <TabsContent value="viewer" className="mt-3">
            <div className="flex items-center justify-center">
              {molstarViewer ?? (
                <div className="border-muted-foreground/25 bg-muted text-muted-foreground flex h-150 w-full items-center justify-center rounded-lg border-2 border-dashed text-sm">
                  Select a structure file in the sidebar to view it.
                </div>
              )}
            </div>
          </TabsContent>

          <TabsContent value="analysis" className="mt-3">
            <AnalysisPanel
              experimentId={experiment.id}
              structureFile={structureFile}
              coordsFile={coordsFile}
              topologyFile={topologyFile}
              topologyRequired={topologyRequired}
              preprocessingMode={preprocessingMode}
              setPreprocessingMode={setPreprocessingMode}
              selectedAnalysis={selectedAnalysis}
              setSelectedAnalysis={setSelectedAnalysis}
            />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}

export default AnalyzeStep
