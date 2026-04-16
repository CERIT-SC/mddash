import { useState } from "react"

import type { FileOption } from "@/util/types"
import { useAmberStatuses, useDeleteAmber } from "@/hooks/use-amber"
import ConfirmDialog from "@/components/ConfirmDialog"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import AmberInputSelector from "../AmberInputSelector"
import AmberRunView from "./AmberRunView"

const AmberRunPanel = (props: WizardStepProps) => {
  const { experiment } = props

  const { data: amberJobs = [], refetch: refetchJobs } = useAmberStatuses(experiment.id)
  const deleteAmber = useDeleteAmber(experiment.id)

  const existingJobs = amberJobs.map((job) => job.prmtop_name)

  const [selectedPrmtop, setSelectedPrmtop] = useState<FileOption | null>(null)
  const [selectedInpcrd, setSelectedInpcrd] = useState<FileOption | null>(null)
  const [selectedMdin, setSelectedMdin] = useState<FileOption | null>(null)
  const [deletePrmtop, setDeletePrmtop] = useState<string | null>(null)
  const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false)

  const allFilesSelected = selectedPrmtop && selectedInpcrd && selectedMdin

  const handleDeletePrmtop = (prmtop: string) => {
    if (existingJobs.includes(prmtop)) {
      setDeletePrmtop(prmtop)
      setConfirmDeleteDialog(true)
    } else {
      setSelectedPrmtop(null)
    }
  }

  const handleConfirmDelete = async () => {
    if (!deletePrmtop) return
    await deleteAmber.mutateAsync(deletePrmtop)
    setSelectedPrmtop(null)
    refetchJobs()
  }

  const handlePrmtopSelected = (file: FileOption | null) => {
    setSelectedPrmtop(file)
    // If selecting a prmtop that has an existing job, show that job
  }

  return (
    <div className="flex w-full flex-col items-center gap-4">
      <div className="flex w-[90%] flex-row gap-4">
        <AmberInputSelector
          experimentId={experiment.id}
          selectedPrmtop={selectedPrmtop?.name ?? null}
          selectedInpcrd={selectedInpcrd?.name ?? null}
          selectedMdin={selectedMdin?.name ?? null}
          onPrmtopSelected={handlePrmtopSelected}
          onInpcrdSelected={setSelectedInpcrd}
          onMdinSelected={setSelectedMdin}
        />

        {allFilesSelected && (
          <div className="flex-1">
            <AmberRunView
              prmtopName={selectedPrmtop.name}
              inpcrdName={selectedInpcrd.name}
              mdinName={selectedMdin.name}
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
