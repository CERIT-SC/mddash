import { useState } from "react"

import { Loader2 } from "lucide-react"

import { useGromacsLogs, useGromacsStatus } from "@/hooks/use-gromacs"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import LogsView from "@/components/LogsView"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import JobStatusDisplay from "./JobStatusDisplay"
import StartForm from "./StartForm"

const NONE_LOG = "__none__"
type LogType = "gmx" | "stdout" | "stderr"

interface RunViewProps extends WizardStepProps {
  tprName: string
  onStartJob: () => void
}

const RunView = (props: RunViewProps) => {
  const { experiment, tprName, onStartJob } = props

  const [logType, setLogType] = useState<LogType | "">("")

  const jobQuery = useGromacsStatus(
    experiment.id,
    tprName,
    // Poll when running
    false // will be handled via shouldPoll below once we have data
  )

  const jobStatus = jobQuery.data ?? null
  const isRunning = jobStatus?.status === "RUNNING"
  const shouldPollJob = !!jobStatus && jobStatus.status !== "TERMINATED" && jobStatus.status !== "ERROR"

  // Separate query for polling
  useGromacsStatus(experiment.id, tprName, shouldPollJob)

  const logsAvailable = !!jobStatus && jobStatus.nsteps !== null
  const shouldRefreshLogs = isRunning

  const logsQuery = useGromacsLogs(experiment.id, tprName, logType as LogType, shouldRefreshLogs)

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
    return <StartForm {...props} onStartJob={handleJobStarted} />
  }

  return (
    <div className="flex flex-col gap-4">
      <JobStatusDisplay jobStatus={jobStatus} />

      {logsAvailable && (
        <div className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold">Logs</h3>
          <div className="flex flex-col gap-3 rounded-md border p-3">
            <div className="flex items-center gap-3">
              <Label htmlFor="log-type-select">Select:</Label>
              <Select
                value={logType || NONE_LOG}
                onValueChange={(val) => setLogType(val === NONE_LOG ? "" : (val as LogType))}
              >
                <SelectTrigger id="log-type-select" className="w-52">
                  <SelectValue placeholder="Log Type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE_LOG}>
                    <em>None</em>
                  </SelectItem>
                  <SelectItem value="gmx">Gromacs Log</SelectItem>
                  <SelectItem value="stdout">Standard Output</SelectItem>
                  <SelectItem value="stderr">Standard Error</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {logType && <LogsView logs={logsQuery.data ?? ""} className="mt-1" />}
          </div>
        </div>
      )}
    </div>
  )
}

export default RunView
