import { lazy, Suspense, useMemo, useState } from "react"

import { getDownloadExperimentFileUrl, useListExperimentFiles } from "@/api/generated/client"
import { type Engine, type Simulation } from "@/api/generated/models"
import { NotebookLauncher, notebookRoleUrl, useNotebook, useNotebookReady } from "@/features/notebook"
import { jobProgressPercent, useSimulationJobQuery } from "@/features/run"
import { InfoBanner } from "@/shared/ui/info-banner"
import {
  AlertDescription,
  AlertTitle,
  Button,
  H4,
  Separator,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@e-infra/design-system"
import { ArrowLeft, ArrowRight, RotateCcw } from "lucide-react"

import { AnalysisPanel } from "./analysis-panel"
import { analysisUnavailableReason } from "./analysis-unavailable"
import { resolveCoordsFormat, resolveStructureFormat } from "./mol-star-formats"

// Lazy so molstar's bundle only loads when this step (and tab) actually opens.
const MolStar = lazy(() => import("./mol-star"))

const VIEWER_HEIGHT = 600
const SIMULATION_POLL_MS = 5000
const fileName = (path: string) => path.split("/").pop() ?? path

type AnalyzeStepProps = {
  experimentId: string
  engine: Engine
  simulation: Simulation
  /** URL-owned picked analysis. */
  selectedAnalysis: string | undefined
  onSelectedAnalysisChange: (analysis: string | undefined) => void
  /** URL-owned tab view. */
  tab: "trajectory" | "analysis"
  onTabChange: (tab: "trajectory" | "analysis") => void
  onStepChange: (step: number) => void
  /** Why Publish is still locked (tooltip on the disabled button); undefined when unlocked. */
  publishReason: string | undefined
  /** Test seam; production callers omit it. */
  pollMs?: number
}

/** Analyze wizard step: trajectory viewer first, then submitted-analysis graphs. */
export function AnalyzeStep({
  experimentId,
  engine,
  simulation,
  selectedAnalysis,
  onSelectedAnalysisChange,
  tab,
  onTabChange,
  onStepChange,
  publishReason,
  pollMs = SIMULATION_POLL_MS,
}: AnalyzeStepProps) {
  const [reloadKey, setReloadKey] = useState(0)

  // The simulation may still be running — results keep changing while it is.
  const jobQuery = useSimulationJobQuery(experimentId, simulation.simulation_path, engine, pollMs)
  const simJob = jobQuery.job
  const simRunning = simJob !== undefined && simJob.is_live
  const simPercent = simJob !== undefined ? jobProgressPercent(simJob) : null

  // Notebook mirrors the setup step's wiring, targeting the analysis notebook.
  const notebookQuery = useNotebook(experimentId)
  const notebook = notebookQuery.data?.status === 200 ? notebookQuery.data.data : undefined
  const { ready, probeFailures } = useNotebookReady(experimentId, notebook)
  const notebookFilesQuery = useListExperimentFiles(experimentId, { ext: "ipynb" }, { query: { retry: false } })
  const notebookFiles = notebookFilesQuery.data?.status === 200 ? notebookFilesQuery.data.data : []
  const openHref = notebook === undefined ? undefined : notebookRoleUrl("analysis", notebookFiles, notebook)

  const viewerUnavailableReason = analysisUnavailableReason(simulation)
  const trajectoryPath = simulation.resolved_files.trajectory ?? null
  const structurePath = simulation.resolved_files.reference_structure ?? null

  const viewer = useMemo(() => {
    if (viewerUnavailableReason !== null || structurePath === null) return null
    return (
      <MolStar
        key={reloadKey}
        width="100%"
        height={VIEWER_HEIGHT}
        structureUrl={getDownloadExperimentFileUrl(experimentId, structurePath)}
        structureFormat={resolveStructureFormat(fileName(structurePath))}
        {...(trajectoryPath !== null
          ? {
              coordsUrl: getDownloadExperimentFileUrl(experimentId, trajectoryPath),
              coordsFormat: resolveCoordsFormat(fileName(trajectoryPath)),
            }
          : {})}
      />
    )
  }, [viewerUnavailableReason, structurePath, trajectoryPath, reloadKey, experimentId])

  return (
    <div className="space-y-6">
      {simRunning && (
        <InfoBanner>
          <AlertTitle>Simulation is still running{simPercent !== null ? ` (${String(simPercent)}%)` : ""}</AlertTitle>
          <AlertDescription>Trajectories and analyses will change as more results are calculated.</AlertDescription>
        </InfoBanner>
      )}

      <div className="space-y-1">
        <H4>Analyze the results</H4>
        <p className="text-text-muted text-sm">
          Each model is a snapshot of your molecule during the simulation. Step through them to see how the structure
          moved over time, or drag inside the viewer to rotate and zoom.
        </p>
      </div>

      <Tabs value={tab} onValueChange={(next) => onTabChange(next as "trajectory" | "analysis")}>
        <div className="flex flex-wrap items-center gap-3">
          <TabsList>
            <TabsTrigger value="trajectory">View Trajectories</TabsTrigger>
            <TabsTrigger value="analysis">Analyze</TabsTrigger>
          </TabsList>
          <span className="text-text-muted text-sm">or</span>
          <NotebookLauncher
            experimentId={experimentId}
            notebook={notebook}
            ready={ready}
            probeFailures={probeFailures}
            openHref={openHref ?? ""}
          />
          {tab === "trajectory" && viewer !== null && (
            <Button size="sm" variant="outline" className="ml-auto" onClick={() => setReloadKey((key) => key + 1)}>
              <RotateCcw aria-hidden />
              Reload Models
            </Button>
          )}
        </div>

        <TabsContent value="analysis" className="mt-4">
          <AnalysisPanel
            experimentId={experimentId}
            engine={engine}
            simulation={simulation}
            selectedAnalysis={selectedAnalysis}
            onSelectedAnalysisChange={onSelectedAnalysisChange}
            pollMs={pollMs}
          />
        </TabsContent>

        <TabsContent value="trajectory" className="mt-4">
          {viewer === null ? (
            <div className="border-border bg-surface text-text-muted flex h-96 w-full items-center justify-center rounded-lg border-2 border-dashed text-sm">
              {viewerUnavailableReason ?? "Select a simulation above to view its structure."}
            </div>
          ) : (
            <Suspense fallback={<Skeleton className="h-[600px] w-full" />}>{viewer}</Suspense>
          )}
        </TabsContent>
      </Tabs>

      <Separator />

      <div className="flex items-center justify-end gap-2">
        <Button type="button" variant="outline" onClick={() => onStepChange(2)}>
          <ArrowLeft aria-hidden />
          Back
        </Button>
        {/* The span wrapper lets the tooltip fire while the button is disabled. */}
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-flex">
              <Button type="button" disabled={publishReason !== undefined} onClick={() => onStepChange(4)}>
                Publish
                <ArrowRight aria-hidden />
              </Button>
            </span>
          </TooltipTrigger>
          {publishReason !== undefined && <TooltipContent>{publishReason}</TooltipContent>}
        </Tooltip>
      </div>
    </div>
  )
}
