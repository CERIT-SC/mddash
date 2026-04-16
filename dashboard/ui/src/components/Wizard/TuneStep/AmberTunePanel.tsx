import { useState } from "react"

import { SkipForward } from "lucide-react"

import { useDeleteTuner, useStopTuner } from "@/hooks/use-tuner"
import { Button } from "@/components/ui/button"
import ConfirmDialog from "@/components/ConfirmDialog"
import { type WizardStepProps } from "@/components/Wizard/Stepper"
import type { FileOption } from "@/util/types"

import AmberInputSelector from "../AmberInputSelector"
import AmberTunerView from "./AmberTunerView"

const AmberTunePanel = (props: WizardStepProps) => {
  const { experiment } = props

  const stopTuner = useStopTuner(experiment.id)
  const deleteTuner = useDeleteTuner(experiment.id)

  const [selectedPrmtop, setSelectedPrmtop] = useState<FileOption | null>(null)
  const [selectedInpcrd, setSelectedInpcrd] = useState<FileOption | null>(null)
  const [selectedMdin, setSelectedMdin] = useState<FileOption | null>(null)
  const [deletePrmtop, setDeletePrmtop] = useState<string | null>(null)
  const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false)
  const [skipDialog, setSkipDialog] = useState(false)

  const allFilesSelected = selectedPrmtop && selectedInpcrd && selectedMdin

  const handleConfirmDelete = async () => {
    if (!deletePrmtop) return
    await deleteTuner.mutateAsync(deletePrmtop)
    setSelectedPrmtop(null)
    refetchJobs()
  }

  const handleStop = async (prmtopName: string) => {
    await stopTuner.mutateAsync(prmtopName)
    refetchJobs()
  }

  // Placeholder for refetchJobs - will be called by child components
  const refetchJobs = () => {
    // The tuner status query will be refetched by the child TunerView component
  }

  return (
    <div className="flex w-full flex-col items-center gap-4">
      <div className="flex w-[90%] flex-row gap-4">
        <AmberInputSelector
          experimentId={experiment.id}
          selectedPrmtop={selectedPrmtop?.name ?? null}
          selectedInpcrd={selectedInpcrd?.name ?? null}
          selectedMdin={selectedMdin?.name ?? null}
          onPrmtopSelected={setSelectedPrmtop}
          onInpcrdSelected={setSelectedInpcrd}
          onMdinSelected={setSelectedMdin}
        />

        {allFilesSelected ? (
          <div className="flex-1">
            <AmberTunerView
              prmtopName={selectedPrmtop.name}
              inpcrdName={selectedInpcrd.name}
              mdinName={selectedMdin.name}
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