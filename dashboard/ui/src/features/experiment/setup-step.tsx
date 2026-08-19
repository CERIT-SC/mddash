import { useEffect, useRef } from "react"

import { useListExperimentFiles, useListSimulations } from "@/api/generated/client"
import type { Experiment, Simulation } from "@/api/generated/models"
import { H4, Tabs, TabsContent, TabsList, TabsTrigger } from "@e-infra/design-system"
import { toast } from "sonner"

import { notebookRoleUrl } from "./notebook"
import { useNotebook, useNotebookReady } from "./notebook-hooks"
import { NotebookLauncher } from "./notebook-launcher"
import { SetupGuide } from "./setup-guide"
import { SimulationForm } from "./simulation-form"
import type { SetupSource } from "./wizard"

/** Heartbeat while the setup step is mounted — the manifest can appear mid-wait. */
const SIMULATIONS_POLL_MS = 5000

type SetupStepProps = {
  experimentId: string
  experiment: Experiment
  simulation: Simulation | undefined
  creating: boolean
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

  // A pipeline run in create mode produces a brand-new tab; adopt it as soon as
  // it surfaces (guarded to the guided tab so a Manual draft is never yanked away).
  const knownPaths = useRef<Set<string> | null>(null)
  useEffect(() => {
    if (polled === undefined || !creating || source !== "notebook") return
    knownPaths.current ??= new Set(polled.map((entry) => entry.simulation_path))
    const fresh = polled.find((entry) => !knownPaths.current!.has(entry.simulation_path))
    if (fresh) {
      // Record before adopting so a pre-navigation re-fire can't adopt twice.
      knownPaths.current!.add(fresh.simulation_path)
      toast.success(`Simulation “${fresh.name}” created by the pipeline`)
      onOpenSimulation(fresh.simulation_path)
    }
  }, [polled, creating, source, onOpenSimulation])

  const handleSaved = (saved: Simulation, created: boolean) => created && onOpenSimulation(saved.simulation_path)

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <H4>Set up your simulation</H4>
        <p className="text-text-muted text-sm">
          Run the setup notebook to generate a simulation manifest, or create one manually. At least one valid setup is
          required to continue.
        </p>
      </div>

      <Tabs value={source} onValueChange={(value) => onSourceChange(value as SetupSource)}>
        <TabsList aria-label="Setup source">
          <TabsTrigger value="notebook">From Notebook</TabsTrigger>
          <TabsTrigger value="manual">Manual</TabsTrigger>
        </TabsList>

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
