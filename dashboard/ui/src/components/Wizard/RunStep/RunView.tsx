import { useState } from "react"

import { Loader2 } from "lucide-react"

import { SELECT_NONE } from "@/util/const"
import { useGromacsLogs, useGromacsStatus } from "@/hooks/use-gromacs"
import { useSimulation } from "@/hooks/use-simulations"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import LogsView from "@/components/LogsView"
import SimulationPreview from "@/components/Wizard/SimulationPreview"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import GmxStartForm from "./GmxStartForm"
import JobStatusDisplay from "./JobStatusDisplay"

type LogType = "gmx" | "stdout" | "stderr"

interface RunViewProps extends WizardStepProps {
  simulationPath: string
  onStartJob: () => void
}

const RunView = (props: RunViewProps) => {
  const { experiment, simulationPath, onStartJob } = props

  const [logType, setLogType] = useState<LogType | "">("")

  const { data: simulation } = useSimulation(experiment.id, simulationPath)
  const jobQuery = useGromacsStatus(experiment.id, simulationPath)

  const jobStatus = jobQuery.data ?? null
  const isRunning = jobStatus?.status === "RUNNING"

  const logsAvailable = !!jobStatus && jobStatus.status !== "PENDING"
  const shouldRefreshLogs = isRunning

  const logsQuery = useGromacsLogs(experiment.id, simulationPath, logType, shouldRefreshLogs)

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
    return (
      <>
        <SimulationPreview simulation={simulation ?? null} />
        <div className="mt-4">
          <GmxStartForm {...props} onStartJob={handleJobStarted} />
        </div>
      </>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <SimulationPreview simulation={simulation ?? null} />
      <JobStatusDisplay jobStatus={jobStatus} />

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
    </div>
  )
}

export default RunView
