import { useEffect, useMemo, useState } from "react"

import { RefreshCw } from "lucide-react"

import {
  AnalysisPreprocessingMode,
  type AnalysisPreprocessingMode as AnalysisPreprocessingModeValue,
  type AnalysisType,
} from "@/util/analysis-types"
import { API_BASE } from "@/util/const"
import { resolveCoordsFormat, resolveStructureFormat } from "@/util/molstar-formats"
import { simulationAnalysisUnavailableReason } from "@/util/simulation"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import MolStar from "@/components/MolStar"
import NotebookController from "@/components/NotebookController"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import AnalysisPanel from "./AnalysisPanel"

const fileUrl = (experimentId: string, path: string) => `${API_BASE}/experiments/${experimentId}/files/${path}`
const fileName = (path: string) => path.split("/").pop() ?? path

const AnalyzeStep = (props: WizardStepProps) => {
  const { experiment } = props

  const [selectedAnalysis, setSelectedAnalysis] = useState<AnalysisType | null>(null)
  const [preprocessingMode, setPreprocessingMode] = useState<AnalysisPreprocessingModeValue>(
    AnalysisPreprocessingMode.AS_IS
  )
  const [reloadKey, setReloadKey] = useState(0)
  const [activeTab, setActiveTab] = useState("viewer")

  const sim = props.selectedSimulation
  const resolved = sim?.resolved_files ?? {}
  const viewerUnavailableReason = simulationAnalysisUnavailableReason(sim, experiment.engine)

  const trajectoryPath = resolved.trajectory ?? null
  const structurePath = resolved.reference_structure ?? null

  const molstarViewer = useMemo(() => {
    if (viewerUnavailableReason) return null
    if (!structurePath) return null
    return (
      <MolStar
        key={reloadKey}
        width="100%"
        height="600px"
        structureUrl={fileUrl(experiment.id, structurePath)}
        structureFormat={resolveStructureFormat(fileName(structurePath))}
        coordsUrl={trajectoryPath ? fileUrl(experiment.id, trajectoryPath) : undefined}
        coordsFormat={trajectoryPath ? resolveCoordsFormat(fileName(trajectoryPath)) : undefined}
      />
    )
  }, [structurePath, trajectoryPath, reloadKey, experiment.id, viewerUnavailableReason])

  useEffect(() => {
    if (sim && !sim.valid) setSelectedAnalysis(null)
  }, [sim])

  return (
    <div className="flex w-full flex-col items-center gap-4">
      <div className="flex w-full flex-col gap-4">
        <NotebookController experimentId={experiment.id} compact inline role="analysis" className="w-full" />

        <Tabs value={activeTab} onValueChange={setActiveTab} className="min-w-0 flex-1">
          <div className="flex items-center justify-between">
            <TabsList>
              <TabsTrigger value="viewer">Trajectory Viewer</TabsTrigger>
              <TabsTrigger value="analysis">Analysis</TabsTrigger>
            </TabsList>
            {trajectoryPath && !viewerUnavailableReason && activeTab === "viewer" && (
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
                  {viewerUnavailableReason ?? "Select a simulation above to view its structure."}
                </div>
              )}
            </div>
          </TabsContent>

          <TabsContent value="analysis" className="mt-3">
            <AnalysisPanel
              experimentId={experiment.id}
              engine={experiment.engine}
              simulation={sim}
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
