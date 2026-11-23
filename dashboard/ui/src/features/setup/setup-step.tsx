import { useEffect, useRef } from "react"

import { useListExperimentFiles, useListSimulations } from "@/api/generated/client"
import type { Experiment, Simulation } from "@/api/generated/models"
import { NotebookLauncher, notebookRoleUrl, pickNotebookFile, useNotebook, useNotebookReady } from "@/features/notebook"
import { SimulationForm } from "@/features/simulation"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@e-infra/design-system"
import { toast } from "sonner"

import { SetupGuide } from "./setup-guide"
import { SetupRunPanel } from "./setup-run"

/** "run" is the headless setup run; workflows without a setup notebook fall back to "notebook". */
export type SetupSource = "run" | "notebook" | "manual"

/** Heartbeat while the setup step is mounted. The manifest can appear mid-wait. */
const SIMULATIONS_POLL_MS = 5000

type SetupStepProps = {
  experimentId: string
  experiment: Experiment
  simulation: Simulation | undefined
  creating: boolean
  /** Whether the experiment already has a simulation (the create tab shows none). */
  hasSimulations: boolean
  /** URL-owned source view (survives the route remount on navigation). */
  source: SetupSource
  onSourceChange: (source: SetupSource) => void
  onOpenSimulation: (simulationPath: string) => void
}

export function SetupStep({
  experimentId,
  experiment,
  simulation,
  creating,
  hasSimulations,
  source,
  onSourceChange,
  onOpenSimulation,
}: SetupStepProps) {
  // Polls: the pipeline writes the manifest from inside the notebook, so only a poll notices it.
  const simulationsQuery = useListSimulations(experimentId, { query: { refetchInterval: SIMULATIONS_POLL_MS } })
  const polled = simulationsQuery.data?.status === 200 ? simulationsQuery.data.data : undefined

  const notebookQuery = useNotebook(experimentId)
  const notebook = notebookQuery.data?.status === 200 ? notebookQuery.data.data : undefined
  const { ready, probeFailures } = useNotebookReady(experimentId, notebook)

  const notebookFilesQuery = useListExperimentFiles(experimentId, { ext: "ipynb" }, { query: { retry: false } })
  const notebookFiles = notebookFilesQuery.data?.status === 200 ? notebookFilesQuery.data.data : []
  const openHref = notebookRoleUrl("setup", notebookFiles, notebook) ?? ""
  const setupNotebook = pickNotebookFile("setup", notebookFiles)
  const view: SetupSource = source === "run" && setupNotebook === undefined ? "notebook" : source
  // One notebook feeds every simulation until #190's per-experiment copies, so a run rewrites its last manifest.
  const runBlocked =
    creating && hasSimulations
      ? "Another simulation needs a parameter change in the notebook, so run it there."
      : simulation?.locked
        ? "A run uses this simulation's files; setup can run again once it is gone."
        : undefined

  // A pipeline run in create mode produces a brand-new tab; adopt it as soon as
  // it surfaces (guarded to the guided tab so a Manual draft is never yanked away).
  const knownPaths = useRef<Set<string> | null>(null)
  useEffect(() => {
    if (polled === undefined || !creating || view === "manual") return
    knownPaths.current ??= new Set(polled.map((entry) => entry.simulation_path))
    const fresh = polled.find((entry) => !knownPaths.current!.has(entry.simulation_path))
    if (fresh) {
      // Record before adopting so a pre-navigation re-fire can't adopt twice.
      knownPaths.current!.add(fresh.simulation_path)
      toast.success(`Simulation “${fresh.name}” created by setup`)
      onOpenSimulation(fresh.simulation_path)
    }
  }, [polled, creating, view, onOpenSimulation])

  const handleSaved = (saved: Simulation, created: boolean) => created && onOpenSimulation(saved.simulation_path)

  return (
    <div className="space-y-6">
      <p className="text-text-muted text-sm">
        Run the setup notebook to generate a simulation manifest, or create one manually. At least one valid setup is
        required to continue.
      </p>

      <Tabs value={view} onValueChange={(value) => onSourceChange(value as SetupSource)}>
        <TabsList aria-label="Setup source">
          {setupNotebook !== undefined && <TabsTrigger value="run">Run setup</TabsTrigger>}
          <TabsTrigger value="notebook">{setupNotebook !== undefined ? "In notebook" : "From Notebook"}</TabsTrigger>
          <TabsTrigger value="manual">Manual</TabsTrigger>
        </TabsList>

        {setupNotebook !== undefined && (
          <TabsContent value="run" className="space-y-6 pt-4">
            <SetupRunPanel
              experimentId={experimentId}
              notebook={setupNotebook.path}
              blockedReason={runBlocked}
              onOpenNotebook={() => onSourceChange("notebook")}
            />
          </TabsContent>
        )}

        <TabsContent value="notebook" className="space-y-6 pt-4">
          <SetupGuide
            experimentId={experimentId}
            notebook={notebook}
            ready={ready}
            probeFailures={probeFailures}
            openHref={openHref}
            manifestExists={simulation !== undefined}
          />
          {simulation !== undefined && (
            <SimulationForm
              experimentId={experimentId}
              engine={experiment.engine}
              simulation={simulation}
              onSaved={handleSaved}
            />
          )}
        </TabsContent>

        <TabsContent value="manual" className="space-y-6 pt-4">
          <div className="space-y-2">
            <p className="text-sm font-semibold">Start the notebook</p>
            <p className="text-text-muted text-sm">This gives you a running environment to prepare the files.</p>
            <NotebookLauncher
              experimentId={experimentId}
              notebook={notebook}
              ready={ready}
              probeFailures={probeFailures}
              openHref={openHref}
            />
          </div>
          <SimulationForm
            experimentId={experimentId}
            engine={experiment.engine}
            simulation={simulation}
            onSaved={handleSaved}
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}
