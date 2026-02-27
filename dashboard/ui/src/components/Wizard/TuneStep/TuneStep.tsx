import { useState } from "react"

import { SkipForward } from "lucide-react"

import { useDeleteTuner, useStopTuner, useTunerStatuses } from "@/hooks/use-tuner"
import { Button } from "@/components/ui/button"
import ConfirmDialog from "@/components/ConfirmDialog"
import { type WizardStepProps } from "@/components/Wizard/Stepper"
import TprSelector from "@/components/Wizard/TprSelector"

import TunerView from "./TunerView"

const TuneStep = (props: WizardStepProps) => {
  const { experiment } = props

  const { data: tunerJobs = [], refetch: refetchJobs } = useTunerStatuses(experiment.id)
  const stopTuner = useStopTuner(experiment.id)
  const deleteTuner = useDeleteTuner(experiment.id)

  const tprFiles = tunerJobs.map((job) => job.tpr_name)
  const existingJobs = tprFiles

  const [selectedTpr, setSelectedTpr] = useState<string | null>(null)
  const [localTprFiles, setLocalTprFiles] = useState<string[]>([])
  const [deleteTpr, setDeleteTpr] = useState<string | null>(null)
  const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false)
  const [skipDialog, setSkipDialog] = useState(false)

  // Merge server jobs into local list
  const allTprFiles = Array.from(new Set([...existingJobs, ...localTprFiles]))

  const handleAddTpr = (tpr: string) => {
    setLocalTprFiles((prev) => (prev.includes(tpr) ? prev : [...prev, tpr]))
    setSelectedTpr(tpr)
  }

  const handleDeleteTpr = (tpr: string) => {
    if (existingJobs.includes(tpr)) {
      setDeleteTpr(tpr)
      setConfirmDeleteDialog(true)
    } else {
      setSelectedTpr(null)
      setLocalTprFiles((prev) => prev.filter((t) => t !== tpr))
    }
  }

  const handleConfirmDelete = async () => {
    if (!deleteTpr) return
    await deleteTuner.mutateAsync(deleteTpr)
    setSelectedTpr(null)
    setLocalTprFiles((prev) => prev.filter((t) => t !== deleteTpr))
    refetchJobs()
  }

  const handleStop = async (tprName: string) => {
    await stopTuner.mutateAsync(tprName)
    refetchJobs()
  }

  return (
    <div className="flex w-full flex-col items-center gap-4">
      <div className="flex w-[90%] flex-row gap-4">
        <TprSelector
          experimentId={experiment.id}
          title="Tuner Jobs"
          addTitle="Add Tuner Job"
          tprFiles={allTprFiles}
          selectedTpr={selectedTpr}
          onAddTpr={handleAddTpr}
          onDeleteTpr={handleDeleteTpr}
          onSelectTpr={setSelectedTpr}
        />

        {selectedTpr ? (
          <div className="flex-1">
            <TunerView tprName={selectedTpr} stopJob={handleStop} onStartTuner={refetchJobs} {...props} />
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

export default TuneStep
