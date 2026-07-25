import { formatDateTime } from "@/util/helpers"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import NotebookController from "@/components/NotebookController"
import SimulationEditor from "@/components/Wizard/SimulationEditor"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

const SetupStep = (props: WizardStepProps) => {
  const { experiment } = props

  const hasValidSimulation = props.simulations.some((s) => s.valid)

  return (
    <div className="flex w-full flex-col gap-5">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <Card className="gap-4 py-5">
          <CardHeader className="flex flex-row items-center justify-between gap-4 px-5">
            <CardTitle className="text-lg">Experiment Details</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 px-5 text-sm md:grid-cols-3">
            <div className="flex flex-col gap-1">
              <span className="text-muted-foreground text-xs">Creation Date</span>
              <span className="font-medium">{formatDateTime(experiment.created_at)}</span>
            </div>
            <div className="flex flex-col gap-1 md:col-span-2">
              <span className="text-muted-foreground text-xs">Creation Method</span>
              <span className="text-muted-foreground">{experiment.source_message}</span>
            </div>
            <div className="flex flex-col gap-1 md:col-span-3">
              <span className="text-muted-foreground text-xs">Notebook Repository</span>
              <span className="text-muted-foreground truncate">{experiment.notebooks_repo || "N/A"}</span>
            </div>
          </CardContent>
        </Card>

        <NotebookController experimentId={experiment.id} compact role="setup" className="w-full" />
      </div>

      <div>
        <SimulationEditor
          experimentId={experiment.id}
          engine={experiment.engine}
          selected={props.selectedSimulation}
          onSelect={(simulation) => props.setSelectedSimulationPath(simulation?.simulation_path ?? null)}
          className="border-0 py-2 shadow-none"
        />
      </div>

      {!hasValidSimulation && (
        <p className="text-muted-foreground text-center text-sm">
          Run the setup notebook to generate a simulation manifest, or create one above. At least one valid simulation
          is required to continue.
        </p>
      )}
    </div>
  )
}

export default SetupStep
