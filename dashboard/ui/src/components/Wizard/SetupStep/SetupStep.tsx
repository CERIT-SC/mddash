import { useState } from "react"

import { SkipForward } from "lucide-react"

import { formatDateTime } from "@/util/helpers"
import { Button } from "@/components/ui/button"
import ConfirmDialog from "@/components/ConfirmDialog"
import NotebookController from "@/components/NotebookController"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

const SetupStep = (props: WizardStepProps) => {
  const { experiment, nextStep } = props
  const [nextStepDialog, setNextStepDialog] = useState(false)

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
