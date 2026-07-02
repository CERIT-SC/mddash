import { useState } from "react"

import { SkipForward } from "lucide-react"

import type { Simulation } from "@/util/types"
import { useSimulations } from "@/hooks/use-simulations"
import { useDeleteTuner, useStopTuner, useTunerStatuses } from "@/hooks/use-tuner"
import { Button } from "@/components/ui/button"
import ConfirmDialog from "@/components/ConfirmDialog"
import SimulationSelector from "@/components/Wizard/SimulationSelector"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import AmberTunerView from "./AmberTunerView"

const AmberTunePanel = (props: WizardStepProps) => {
  const { experiment } = props

  const { data: tunerJobs = [], refetch: refetchJobs } = useTunerStatuses(experiment.id)
  const { data: simulations = [], isLoading } = useSimulations(experiment.id)
  const stopTuner = useStopTuner(experiment.id)
  const deleteTuner = useDeleteTuner(experiment.id)

  const [selected, setSelected] = useState<Simulation | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false)
  const [skipDialog, setSkipDialog] = useState(false)

  const handleDelete = (sim: Simulation) => {
    if (tunerJobs.some((j) => j.simulation_path === sim.simulation_path)) {
      setDeleteTarget(sim.simulation_path)
      setConfirmDeleteDialog(true)
    } else {
      setSelected(null)
    }
  }

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return
    await deleteTuner.mutateAsync(deleteTarget)
    setSelected(null)
    refetchJobs()
  }

  const handleStop = async (simulationPath: string) => {
    await stopTuner.mutateAsync(simulationPath)
    refetchJobs()
  }

  return (
    <div className="flex w-full flex-col items-center gap-4">
      <div className="flex w-[90%] flex-row gap-4">
        <SimulationSelector
          simulations={simulations}
          selectedPath={selected?.simulation_path ?? null}
          loading={isLoading}
          onSelect={(sim) => {
            if (sim) handleDelete(sim)
            setSelected(sim)
          }}
        />

        {selected ? (
          <div className="flex-1">
            <AmberTunerView
              simulationPath={selected.simulation_path}
              stopJob={handleStop}
              onStartTuner={refetchJobs}
              {...props}
            />
          </div>
        ) : (
          <div className="flex flex-1 items-start justify-end">
            <Button
              variant="outline"
              className="text-destructive border-destructive hover:bg-destructive hover:text-destructive-foreground"
              onClick={() => setSkipDialog(true)}
            >
              <SkipForward className="mr-1 h-4 w-4" />
              Skip Tuning
            </Button>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={skipDialog}
        setOpen={setSkipDialog}
        title="Skip Tuning?"
        message="Are you sure you want to skip tuning? Your simulation may run slowly without tuning."
        onConfirm={props.nextStep}
      />

      <ConfirmDialog
        open={confirmDeleteDialog}
        setOpen={setConfirmDeleteDialog}
        onConfirm={handleConfirmDelete}
        message="Are you sure you want to delete this tuning job? The data will be lost."
      />
    </div>
  )
}

export default AmberTunePanel
