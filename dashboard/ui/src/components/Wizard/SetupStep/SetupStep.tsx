import { useState } from "react"

import { SkipForward } from "lucide-react"

import { formatDateTime } from "@/util/helpers"
import type { Simulation } from "@/util/types"
import { useSimulations } from "@/hooks/use-simulations"
import { Button } from "@/components/ui/button"
import ConfirmDialog from "@/components/ConfirmDialog"
import NotebookController from "@/components/NotebookController"
import SimulationEditor from "@/components/Wizard/SimulationEditor"
import SimulationSelector from "@/components/Wizard/SimulationSelector"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

const SetupStep = (props: WizardStepProps) => {
  const { experiment, nextStep } = props
  const [nextStepDialog, setNextStepDialog] = useState(false)
  const [selected, setSelected] = useState<Simulation | null>(null)

  const { data: simulations = [], isLoading } = useSimulations(experiment.id)
  const hasValidSimulation = simulations.some((s) => s.valid)

  return (
    <div className="flex flex-col items-center gap-8">
      <div className="flex w-[90%] flex-col gap-2">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">Experiment Details</h3>
          {experiment.step === 0 && (
            <Button
              variant="outline"
              className="text-destructive border-destructive hover:bg-destructive hover:text-destructive-foreground"
              onClick={() => setNextStepDialog(true)}
              disabled={!hasValidSimulation}
            >
              <SkipForward className="mr-1 h-4 w-4" />
              Skip Setup
            </Button>
          )}
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium">Creation Date:</span>
          <span className="text-muted-foreground">{formatDateTime(experiment.created_at)}</span>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium">Creation Method:</span>
          <span className="text-muted-foreground">{experiment.source_message}</span>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium">Notebook Repository:</span>
          <span className="text-muted-foreground">{experiment.notebooks_repo || "N/A"}</span>
        </div>
      </div>

      <NotebookController experimentId={experiment.id} />

      <div className="flex w-[90%] flex-row gap-4">
        <SimulationSelector
          simulations={simulations}
          selectedPath={selected?.simulation_path ?? null}
          loading={isLoading}
          onSelect={setSelected}
        />
        <div className="flex-1">
          <SimulationEditor
            experimentId={experiment.id}
            engine={experiment.engine}
            selected={selected}
            onSelect={setSelected}
          />
        </div>
      </div>

      {!hasValidSimulation && (
        <p className="text-muted-foreground text-center text-sm">
          Run the setup notebook to generate a simulation manifest, or create one above. At least one valid simulation
          is required to continue.
        </p>
      )}

      <ConfirmDialog
        open={nextStepDialog}
        setOpen={setNextStepDialog}
        title="Complete Setup?"
        message="Are you sure you want to proceed to the next step? Setup doesn't appear to be complete in the notebook. Stuff may break later."
        onConfirm={nextStep}
      />
    </div>
  )
}

export default SetupStep
