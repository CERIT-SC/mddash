import { useState } from "react"

import { useAmberStatuses, useDeleteAmber } from "@/hooks/use-amber"
import ConfirmDialog from "@/components/ConfirmDialog"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import AmberSelector, { type AmberJobEntry } from "../AmberSelector"
import AmberRunView from "./AmberRunView"

const AmberRunPanel = (props: WizardStepProps) => {
  const { experiment } = props

  const { data: amberJobs = [], refetch: refetchJobs } = useAmberStatuses(experiment.id)
  const deleteAmber = useDeleteAmber(experiment.id)

  const existingPrmtops = amberJobs.map((job) => job.prmtop_name)

  const [selectedPrmtop, setSelectedPrmtop] = useState<string | null>(null)
  const [localJobs, setLocalJobs] = useState<AmberJobEntry[]>([])
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false)

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
    await deleteAmber.mutateAsync(deleteTarget)
    if (selectedPrmtop === deleteTarget) setSelectedPrmtop(null)
    setLocalJobs((prev) => prev.filter((j) => j.prmtopName !== deleteTarget))
    refetchJobs()
  }

  const selectedJob =
    amberJobs.find((j) => j.prmtop_name === selectedPrmtop) ?? localJobs.find((j) => j.prmtopName === selectedPrmtop)

  const selectedInpcrd =
    "inpcrd_name" in (selectedJob ?? {})
      ? (selectedJob as (typeof amberJobs)[0]).inpcrd_name
      : ((selectedJob as AmberJobEntry | undefined)?.inpcrdName ?? "")

  const selectedMdin =
    "mdin_name" in (selectedJob ?? {})
      ? (selectedJob as (typeof amberJobs)[0]).mdin_name
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

        {selectedPrmtop && selectedJob && (
          <div className="flex-1">
            <AmberRunView
              prmtopName={selectedPrmtop}
              inpcrdName={selectedInpcrd}
              mdinName={selectedMdin}
              onStartJob={refetchJobs}
              {...props}
            />
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirmDeleteDialog}
        setOpen={setConfirmDeleteDialog}
        onConfirm={handleConfirmDelete}
        message="Are you sure you want to delete this AMBER job? The data will be lost."
      />
    </div>
  )
}

export default AmberRunPanel
