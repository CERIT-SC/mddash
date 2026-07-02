import { useState } from "react"

import type { Simulation } from "@/util/types"
import { useDeleteGmx, useGromacsStatuses } from "@/hooks/use-gromacs"
import { useSimulations } from "@/hooks/use-simulations"
import ConfirmDialog from "@/components/ConfirmDialog"
import SimulationSelector from "@/components/Wizard/SimulationSelector"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import RunView from "./RunView"

const GmxRunPanel = (props: WizardStepProps) => {
  const { experiment } = props

  const { data: gromacsJobs = [], refetch: refetchJobs } = useGromacsStatuses(experiment.id)
  const { data: simulations = [], isLoading } = useSimulations(experiment.id)
  const deleteGmx = useDeleteGmx(experiment.id)

  const [selected, setSelected] = useState<Simulation | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false)

  const handleSelect = (sim: Simulation | null) => {
    if (!sim) {
      setSelected(null)
      return
    }
    if (gromacsJobs.some((j) => j.simulation_path === sim.simulation_path)) {
      setDeleteTarget(sim.simulation_path)
      setConfirmDeleteDialog(true)
      return
    }
    setSelected(sim)
  }

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return
    await deleteGmx.mutateAsync(deleteTarget)
    setSelected(null)
    refetchJobs()
  }

  return (
    <div className="flex w-full flex-col items-center gap-4">
      <div className="flex w-[90%] flex-row gap-4">
        <SimulationSelector
          simulations={simulations}
          selectedPath={selected?.simulation_path ?? null}
          loading={isLoading}
          onSelect={handleSelect}
        />

        {selected && (
          <div className="flex-1">
            <RunView simulationPath={selected.simulation_path} onStartJob={refetchJobs} {...props} />
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirmDeleteDialog}
        setOpen={setConfirmDeleteDialog}
        onConfirm={handleConfirmDelete}
        message="Are you sure you want to delete this GROMACS job? The data will be lost."
      />
    </div>
  )
}

export default GmxRunPanel
