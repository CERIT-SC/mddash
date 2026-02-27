import { useState } from "react"

import { Loader2, Pause, Play } from "lucide-react"

import { type TunerTrial } from "@/util/types"
import { useRunTuner, useTunerStatus } from "@/hooks/use-tuner"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import ConfirmDialog from "@/components/ConfirmDialog"
import StartForm from "@/components/Wizard/RunStep/StartForm"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import TunerTable from "./TunerTable"

const DEFAULT_NSTEPS = 25000

interface TunerViewProps extends WizardStepProps {
  tprName: string
  stopJob: (tprName: string) => void
  onStartTuner?: () => void
}

const TunerView = (props: TunerViewProps) => {
  const { experiment, tprName, stopJob, nextStep, changeStep, onStartTuner } = props

  const [selectedTrial, setSelectedTrial] = useState<TunerTrial | null>(null)
  const [nsteps, setNsteps] = useState<number | "">(DEFAULT_NSTEPS)
  const [confirmStopDialog, setConfirmStopDialog] = useState(false)

  const runTuner = useRunTuner(experiment.id)

  const tunerStarted_condition = (tuner: ReturnType<typeof useTunerStatus>["data"]) =>
    !!tuner && !tuner.error_message && tuner.tuner_status !== "ERROR"

  const { data: tuner, isLoading } = useTunerStatus(
    experiment.id,
    tprName,
    // Poll when running and not stopped
    false // will be updated below via shouldPoll derived from data
  )

  const tunerStarted = tunerStarted_condition(tuner)
  const tunerStopped = tuner?.is_stopped || false
  const shouldPoll = tunerStarted && !tunerStopped && tuner?.tuner_status !== "TERMINATED"

  // Re-query with polling when needed
  const { data: polledTuner } = useTunerStatus(experiment.id, tprName, shouldPoll)
  const activeTuner = shouldPoll ? polledTuner : tuner

  const handleRunTuner = () => {
    const actualNsteps = nsteps === "" ? DEFAULT_NSTEPS : nsteps
    runTuner.mutate({ tprName, nsteps: actualNsteps }, { onSuccess: () => onStartTuner?.() })
  }

  const goToRunStep = () => {
    if (experiment.step < 2) nextStep()
    else changeStep(2)
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="text-muted-foreground h-6 w-6 animate-spin" />
      </div>
    )
  }

  const displayTuner = activeTuner ?? tuner
  const displayStarted = tunerStarted_condition(displayTuner)
  const displayStopped = displayTuner?.is_stopped || false

  return (
    <>
      {displayStarted ? (
        <div className="flex flex-col gap-4">
          <TunerTable
            rows={displayTuner?.trials || []}
            selectedTrial={selectedTrial}
            setSelectedTrial={setSelectedTrial}
            tunerStopped={displayStopped}
          />

          {!displayStopped && (
            <div className="flex justify-end gap-2">
              <Button
                variant="default"
                className="bg-yellow-500 text-white hover:bg-yellow-600"
                onClick={() => setConfirmStopDialog(true)}
              >
                <Pause className="mr-1 h-4 w-4" />
                Stop
              </Button>
            </div>
          )}

          {selectedTrial && (
            <StartForm
              onStartJob={goToRunStep}
              np={selectedTrial.np}
              ntomp={selectedTrial.ntomp}
              nb={selectedTrial.nb}
              pme={selectedTrial.pme}
              {...props}
            />
          )}
        </div>
      ) : (
        <div className="flex h-full flex-col items-center justify-center gap-4">
          {displayTuner?.error_message && (
            <div className="border-destructive bg-destructive/10 text-destructive w-full rounded-md border p-3 text-sm">
              <strong>Error:</strong> {displayTuner.error_message}
            </div>
          )}

          {!displayTuner?.error_message && (
            <h3 className="text-lg font-semibold">Configure tuning job for {tprName}</h3>
          )}

          {(!displayTuner || displayTuner.error_message) && (
            <Card className="w-fit">
              <CardContent className="flex flex-col items-center gap-4 pt-4">
                <div className="flex w-72 flex-col gap-1">
                  <Label htmlFor="nsteps-input">Number of steps (nsteps)</Label>
                  <Input
                    id="nsteps-input"
                    type="number"
                    value={nsteps}
                    onChange={(e) => {
                      const val = e.target.value
                      setNsteps(val === "" ? "" : parseInt(val) || "")
                    }}
                  />
                </div>
                <Button variant="default" onClick={handleRunTuner} disabled={runTuner.isPending} className="w-48">
                  {runTuner.isPending ? (
                    <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="mr-1 h-4 w-4" />
                  )}
                  Start tune job
                </Button>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirmStopDialog}
        setOpen={setConfirmStopDialog}
        confirmColor="warning"
        onConfirm={async () => {
          await stopJob(tprName)
        }}
        message="Are you sure you want to stop the tuning job? You cannot resume it, but data will be preserved."
      />
    </>
  )
}

export default TunerView
