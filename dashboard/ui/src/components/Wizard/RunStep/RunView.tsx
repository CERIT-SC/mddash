import { useState } from "react"

import { Loader2, Trash2 } from "lucide-react"

import { SELECT_NONE } from "@/util/const"
import { simulationLaunchUnavailableReason } from "@/util/simulation"
import { useDeleteGmx, useGromacsLogs, useGromacsStatus } from "@/hooks/use-gromacs"
import { useSimulation } from "@/hooks/use-simulations"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import ConfirmDialog from "@/components/ConfirmDialog"
import LogsView from "@/components/LogsView"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import GmxStartForm from "./GmxStartForm"
import JobStatusDisplay from "./JobStatusDisplay"

type LogType = "gmx" | "stdout" | "stderr"

interface RunViewProps extends WizardStepProps {
  simulationPath: string
  hasSimulationJob: boolean
  onStartJob: () => void
}

const RunView = (props: RunViewProps) => {
  const { experiment, simulationPath, hasSimulationJob, onStartJob } = props

  const [logType, setLogType] = useState<LogType | "">("")
  const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false)

  const { data: simulation } = useSimulation(experiment.id, simulationPath)
  const jobQuery = useGromacsStatus(experiment.id, simulationPath, hasSimulationJob)
  const deleteGmx = useDeleteGmx(experiment.id)

  const jobStatus = jobQuery.data ?? null
  const isRunning = jobStatus?.status === "RUNNING"

  const logsAvailable = !!jobStatus && jobStatus.status !== "PENDING"
  const shouldRefreshLogs = isRunning

  const logsQuery = useGromacsLogs(experiment.id, simulationPath, logType, shouldRefreshLogs)
  const unavailableReason = simulationLaunchUnavailableReason(simulation ?? null, experiment.engine)

  const handleJobStarted = () => {
    jobQuery.refetch()
    onStartJob()
  }

  if (jobQuery.isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="text-muted-foreground h-6 w-6 animate-spin" />
      </div>
    )
  }

  if (!jobStatus) {
    return <GmxStartForm {...props} onStartJob={handleJobStarted} disabledReason={unavailableReason} />
  }

  return (
    <div className="flex flex-col gap-4">
      <JobStatusDisplay
        jobStatus={jobStatus}
        actions={
          <Button
            variant="outline"
            size="sm"
            className="text-destructive border-destructive hover:bg-destructive hover:text-destructive-foreground"
            onClick={() => setConfirmDeleteDialog(true)}
          >
            <Trash2 className="mr-1 h-4 w-4" />
            Delete job
          </Button>
        }
      />

      {logsAvailable && (
        <div className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold">Logs</h3>
          <div className="flex flex-col gap-3 rounded-md border p-3">
            <div className="flex items-center gap-3">
              <Label htmlFor="log-type-select">Select:</Label>
              <Select
                value={logType || SELECT_NONE}
                onValueChange={(val) => setLogType(val === SELECT_NONE ? "" : (val as LogType))}
              >
                <SelectTrigger id="log-type-select" className="w-52">
                  <SelectValue placeholder="Log Type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={SELECT_NONE}>
                    <em>None</em>
                  </SelectItem>
                  <SelectItem value="gmx">Gromacs Log</SelectItem>
                  <SelectItem value="stdout">Standard Output</SelectItem>
                  <SelectItem value="stderr">Standard Error</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {logType && <LogsView logs={logsQuery.data ?? ""} isLoading={logsQuery.isLoading} className="mt-1" />}
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmDeleteDialog}
        setOpen={setConfirmDeleteDialog}
        confirmColor="destructive"
        onConfirm={async () => {
          await deleteGmx.mutateAsync(simulationPath)
        }}
        message="Delete this simulation job? This cannot be undone."
      />
    </div>
  )
}

export default RunView
