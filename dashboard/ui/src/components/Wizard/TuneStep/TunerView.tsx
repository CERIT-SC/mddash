import { useState } from "react"

import { Loader2, Pause, Play } from "lucide-react"

import { simulationLaunchUnavailableReason } from "@/util/simulation"
import { type GmxTunerTrial } from "@/util/types"
import { useSimulation } from "@/hooks/use-simulations"
import { useRunTuner, useTunerStatus } from "@/hooks/use-tuner"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import ConfirmDialog from "@/components/ConfirmDialog"
import { StartForm } from "@/components/Wizard/RunStep/GmxStartForm"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import TunerTable from "./TunerTable"

const DEFAULT_NSTEPS = 25000

interface TunerViewProps extends WizardStepProps {
  simulationPath: string
  hasTunerJob: boolean
  stopJob: (simulationPath: string) => void
  onStartTuner?: () => void
}

const TunerView = (props: TunerViewProps) => {
  const { experiment, simulationPath, hasTunerJob, stopJob, nextStep, changeStep, onStartTuner } = props

  const [selectedTrial, setSelectedTrial] = useState<GmxTunerTrial | null>(null)
  const [nsteps, setNsteps] = useState<number | "">(DEFAULT_NSTEPS)
  const [confirmStopDialog, setConfirmStopDialog] = useState(false)

  const runTuner = useRunTuner(experiment.id)
  const { data: simulation } = useSimulation(experiment.id, simulationPath)

  const tunerStarted_condition = (tuner: ReturnType<typeof useTunerStatus>["data"]) =>
    !!tuner && !tuner.error_message && tuner.tuner_status !== "ERROR"

  const { data: tuner, isLoading } = useTunerStatus(experiment.id, simulationPath, hasTunerJob)

  const handleRunTuner = () => {
    const actualNsteps = nsteps === "" ? DEFAULT_NSTEPS : nsteps
    runTuner.mutate({ simulationPath, nsteps: actualNsteps }, { onSuccess: () => onStartTuner?.() })
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

  const displayStarted = tunerStarted_condition(tuner)
  const displayStopped = tuner?.is_stopped || false
  const trials = (tuner?.trials || []) as GmxTunerTrial[]
  const unavailableReason = simulationLaunchUnavailableReason(simulation ?? null, experiment.engine)

  return (
    <>
      {displayStarted ? (
        <div className="flex flex-col gap-4">
          <TunerTable
            rows={trials}
            selectedTrial={selectedTrial}
            setSelectedTrial={setSelectedTrial}
            tunerStopped={displayStopped}
            experimentId={experiment.id}
            simulationPath={simulationPath}
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
        <div className="flex flex-col items-center justify-center gap-4">
          {tuner?.error_message && (
            <div className="border-destructive bg-destructive/10 text-destructive w-full rounded-md border p-3 text-sm">
              <strong>Error:</strong> {tuner.error_message}
            </div>
          )}

          {!tuner?.error_message && <h3 className="text-lg font-semibold">Configure tuning job</h3>}

          {(!tuner || tuner.error_message) && (
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
                <Button
                  variant="default"
                  onClick={handleRunTuner}
                  disabled={runTuner.isPending || !!unavailableReason}
                  className="w-48"
                >
                  {runTuner.isPending ? (
                    <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="mr-1 h-4 w-4" />
                  )}
                  Start tune job
                </Button>
                {unavailableReason && (
                  <p className="text-muted-foreground max-w-72 text-center text-xs">{unavailableReason}</p>
                )}
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
          await stopJob(simulationPath)
        }}
        message="Are you sure you want to stop the tuning job? Results collected so far will be saved, but any trials still in progress will be lost. This cannot be undone."
      />
    </>
  )
}

export default TunerView
