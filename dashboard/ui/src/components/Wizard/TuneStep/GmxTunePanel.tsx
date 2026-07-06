import { useState } from "react"

import { SkipForward } from "lucide-react"

import { useStopTuner, useTunerStatuses } from "@/hooks/use-tuner"
import { Button } from "@/components/ui/button"
import ConfirmDialog from "@/components/ConfirmDialog"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import TunerView from "./TunerView"

const GmxTunePanel = (props: WizardStepProps) => {
  const { experiment } = props

  const { data: tunerJobs = [], refetch: refetchJobs } = useTunerStatuses(experiment.id)
  const stopTuner = useStopTuner(experiment.id)

  const [skipDialog, setSkipDialog] = useState(false)

  const handleStop = async (simulationPath: string) => {
    await stopTuner.mutateAsync(simulationPath)
    refetchJobs()
  }

  return (
    <div className="flex w-full flex-col items-center gap-4">
      <div className="flex w-full flex-col gap-4">
        {props.selectedSimulation ? (
          <TunerView
            simulationPath={props.selectedSimulation.simulation_path}
            hasTunerJob={tunerJobs.some((job) => job.simulation_path === props.selectedSimulation?.simulation_path)}
            stopJob={handleStop}
            onStartTuner={refetchJobs}
            {...props}
          />
        ) : (
          <div className="flex items-start justify-end">
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
    </div>
  )
}

export default GmxTunePanel
