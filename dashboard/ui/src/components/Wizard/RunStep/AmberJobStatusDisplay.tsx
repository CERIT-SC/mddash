import { statusBadgeClass } from "@/lib/status"
import { cn } from "@/lib/utils"
import { formatDuration } from "@/util/helpers"
import { getJobStatusVariant, type AmberJob } from "@/util/types"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"

interface AmberJobStatusDisplayProps {
  jobStatus: AmberJob
}

const AmberJobStatusDisplay = ({ jobStatus }: AmberJobStatusDisplayProps) => {
  const isRunningWithProgress =
    jobStatus.status === "RUNNING" && jobStatus.nsteps !== null && jobStatus.nsteps_done !== null

  const progressPercentage = isRunningWithProgress ? (jobStatus.nsteps_done! / jobStatus.nsteps!) * 100 : 0
  const variant = getJobStatusVariant(jobStatus.status)

  return (
    <div className="flex w-full flex-col gap-4">
      {/* Status card */}
      <div className="flex flex-col gap-3 rounded-md border p-3">
        <div className="flex items-center justify-center gap-2">
          <span className="text-sm font-medium">Status</span>
          <Badge variant="outline" className={cn("text-xs", statusBadgeClass(variant))}>
            {jobStatus.status}
          </Badge>
        </div>

        {isRunningWithProgress && (
          <div className="flex flex-col items-center gap-1">
            <span className="text-muted-foreground text-sm">Progress</span>
            <span className="text-2xl font-bold">{progressPercentage.toFixed(1)}%</span>
            <Progress value={progressPercentage} className="h-3 w-full rounded" />
            <span className="text-muted-foreground text-xs">
              {jobStatus.nsteps_done!.toLocaleString()} / {jobStatus.nsteps!.toLocaleString()} steps
            </span>
          </div>
        )}
      </div>

      {/* Job summary (after completion) */}
      {jobStatus.status === "TERMINATED" && (
        <>
          <h3 className="text-sm font-semibold">Job Summary</h3>
          <div className="grid grid-cols-2 gap-2">
            {jobStatus.performance && (
              <div className="rounded-md border p-3">
                <p className="text-muted-foreground text-xs">Performance</p>
                <p className="text-sm">{jobStatus.performance.toFixed(2)} ns/day</p>
              </div>
            )}
            {jobStatus.start_timestamp && jobStatus.finish_timestamp && (
              <div className="rounded-md border p-3">
                <p className="text-muted-foreground text-xs">Total Runtime</p>
                <p className="text-sm">{formatDuration(jobStatus.finish_timestamp - jobStatus.start_timestamp)}</p>
              </div>
            )}
          </div>
        </>
      )}

      {/* Simulation parameters */}
      <h3 className="text-sm font-semibold">Simulation Parameters</h3>
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-md border p-3">
          <p className="text-muted-foreground text-xs">Binary</p>
          <p className="text-sm">{jobStatus.binary}</p>
        </div>
        <div className="rounded-md border p-3">
          <p className="text-muted-foreground text-xs">Ewald</p>
          <p className="text-sm">{jobStatus.ewald}</p>
        </div>
        <div className="rounded-md border p-3">
          <p className="text-muted-foreground text-xs">Processes</p>
          <p className="text-sm">
            {jobStatus.np} × {jobStatus.ntomp} threads
          </p>
        </div>
        {jobStatus.extra_args && (
          <div className="col-span-2 rounded-md border p-3">
            <p className="text-muted-foreground text-xs">Extra Arguments</p>
            <p className="text-sm">{jobStatus.extra_args}</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default AmberJobStatusDisplay