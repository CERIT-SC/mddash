import { useState } from "react"

import { SkipForward } from "lucide-react"

import { useDeleteTuner, useStopTuner, useTunerStatuses } from "@/hooks/use-tuner"
import { Button } from "@/components/ui/button"
import ConfirmDialog from "@/components/ConfirmDialog"
import AmberSelector, { type AmberJobEntry } from "@/components/Wizard/AmberSelector"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import AmberTunerView from "./AmberTunerView"

const AmberTunePanel = (props: WizardStepProps) => {
  const { experiment } = props

  const { data: tunerJobs = [], refetch: refetchJobs } = useTunerStatuses(experiment.id)
  const stopTuner = useStopTuner(experiment.id)
  const deleteTuner = useDeleteTuner(experiment.id)

  const existingPrmtops = tunerJobs.map((job) => job.tpr_name)

  const [selectedPrmtop, setSelectedPrmtop] = useState<string | null>(null)
  const [localJobs, setLocalJobs] = useState<AmberJobEntry[]>([])
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false)
  const [skipDialog, setSkipDialog] = useState(false)

  const allPrmtops = Array.from(new Set([...existingPrmtops, ...localJobs.map((j) => j.prmtopName)]))

  const handleAddJob = (entry: AmberJobEntry) => {
    setLocalJobs((prev) => (prev.some((j) => j.prmtopName === entry.prmtopName) ? prev : [...prev, entry]))
    setSelectedPrmtop(entry.prmtopName)
  }

  const handleDeleteJob = (prmtopName: string) => {
    if (existingPrmtops.includes(prmtopName)) {
      setDeleteTarget(prmtopName)
      setConfirmDeleteDialog(true)
    } else {
      if (selectedPrmtop === prmtopName) setSelectedPrmtop(null)
      setLocalJobs((prev) => prev.filter((j) => j.prmtopName !== prmtopName))
    }
  }

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return
    await deleteTuner.mutateAsync(deleteTarget)
    if (selectedPrmtop === deleteTarget) setSelectedPrmtop(null)
    setLocalJobs((prev) => prev.filter((j) => j.prmtopName !== deleteTarget))
    refetchJobs()
  }

  const handleStop = async (prmtopName: string) => {
    await stopTuner.mutateAsync(prmtopName)
    refetchJobs()
  }

  const selectedJob =
    tunerJobs.find((j) => j.tpr_name === selectedPrmtop) ?? localJobs.find((j) => j.prmtopName === selectedPrmtop)

  const selectedInpcrd =
    selectedJob && "inpcrd_name" in selectedJob
      ? (selectedJob.inpcrd_name ?? "")
      : ((selectedJob as AmberJobEntry | undefined)?.inpcrdName ?? "")

  const selectedMdin =
    selectedJob && "mdin_name" in selectedJob
      ? (selectedJob.mdin_name ?? "")
      : ((selectedJob as AmberJobEntry | undefined)?.mdinName ?? "")

  return (
    <div className="flex w-full flex-col items-center gap-4">
      <div className="flex w-[90%] flex-row gap-4">
        <AmberSelector
          experimentId={experiment.id}
          jobs={allPrmtops}
          selectedPrmtop={selectedPrmtop}
          onAddJob={handleAddJob}
          onDeleteJob={handleDeleteJob}
          onSelectJob={setSelectedPrmtop}
        />

        {selectedPrmtop && selectedJob ? (
          <div className="flex-1">
            <AmberTunerView
              prmtopName={selectedPrmtop}
              inpcrdName={selectedInpcrd}
              mdinName={selectedMdin}
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
