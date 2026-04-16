import { useState } from "react"

import { Loader2, Pause, Play } from "lucide-react"

import { type AmberTunerTrial } from "@/util/types"
import { useRunAmberTuner, useTunerStatus } from "@/hooks/use-tuner"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import ConfirmDialog from "@/components/ConfirmDialog"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import AmberTunerTable from "./AmberTunerTable"

const DEFAULT_NSTEPS = 25000

interface AmberTunerViewProps extends WizardStepProps {
  prmtopName: string
  inpcrdName: string
  mdinName: string
  stopJob: (prmtopName: string) => void
  onStartTuner?: () => void
}

const AmberTunerView = (props: AmberTunerViewProps) => {
  const { experiment, prmtopName, inpcrdName, mdinName, stopJob, nextStep, changeStep, onStartTuner } = props

  const [selectedTrial, setSelectedTrial] = useState<AmberTunerTrial | null>(null)
  const [nsteps, setNsteps] = useState<number | "">(DEFAULT_NSTEPS)
  const [confirmStopDialog, setConfirmStopDialog] = useState(false)

  const runAmberTuner = useRunAmberTuner(experiment.id)

  const tunerStarted_condition = (tuner: ReturnType<typeof useTunerStatus>["data"]) =>
    !!tuner && !tuner.error_message && tuner.tuner_status !== "ERROR"

  const { data: tuner, isLoading } = useTunerStatus(experiment.id, prmtopName)

  const handleRunTuner = () => {
    const actualNsteps = nsteps === "" ? DEFAULT_NSTEPS : nsteps
    runAmberTuner.mutate(
      { prmtopName, inpcrdName, mdinName, nsteps: actualNsteps },
      { onSuccess: () => onStartTuner?.() }
    )
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

  // Cast trials to AmberTunerTrial[] since we know this is AMBER engine
  const trials = (tuner?.trials || []) as AmberTunerTrial[]

  return (
    <>
      {displayStarted ? (
        <div className="flex flex-col gap-4">
          <AmberTunerTable
            rows={trials}
            selectedTrial={selectedTrial}
            setSelectedTrial={setSelectedTrial}
            tunerStopped={displayStopped}
            experimentId={experiment.id}
            prmtopName={prmtopName}
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
            <Card className="w-fit">
              <CardContent className="flex flex-col gap-3 pt-4">
                <h3 className="text-sm font-semibold">Selected Configuration</h3>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <span className="text-muted-foreground">Binary:</span> {selectedTrial.binary}
                  </div>
                  <div>
                    <span className="text-muted-foreground">Ewald:</span> {selectedTrial.ewald}
                  </div>
                  <div>
                    <span className="text-muted-foreground">NP:</span> {selectedTrial.np}
                  </div>
                  <div>
                    <span className="text-muted-foreground">NTOMP:</span> {selectedTrial.ntomp}
                  </div>
                  {selectedTrial.performance !== null && (
                    <div className="col-span-2">
                      <span className="text-muted-foreground">Performance:</span> {selectedTrial.performance.toFixed(2)}{" "}
                      ns/day
                    </div>
                  )}
                </div>
                <Button onClick={goToRunStep} className="w-full">
                  Proceed to Run Step
                </Button>
              </CardContent>
            </Card>
          )}
        </div>
      ) : (
        <div className="flex h-full flex-col items-center justify-center gap-4">
          {tuner?.error_message && (
            <div className="border-destructive bg-destructive/10 text-destructive w-full rounded-md border p-3 text-sm">
              <strong>Error:</strong> {tuner.error_message}
            </div>
          )}

          {!tuner?.error_message && <h3 className="text-lg font-semibold">Configure tuning job for {prmtopName}</h3>}

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
                <Button variant="default" onClick={handleRunTuner} disabled={runAmberTuner.isPending} className="w-48">
                  {runAmberTuner.isPending ? (
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
          await stopJob(prmtopName)
        }}
        message="Are you sure you want to stop the tuning job? Results collected so far will be saved, but any trials still in progress will be lost. This cannot be undone."
      />
    </>
  )
}

export default AmberTunerView
