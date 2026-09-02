import { JobStatus, type SimulationJob } from "@/api/generated/models"
import { formatTime } from "@/shared/format"
import { Button, Progress } from "@e-infra/design-system"
import { Clock, LoaderCircle, RotateCcw, Square } from "lucide-react"

import { jobProgressPercent } from "./use-simulation-job"

type RunProgressProps = {
  job: SimulationJob
  /** A stop/re-run mutation is in flight — buttons stay disabled meanwhile. */
  busy: boolean
  onStop: () => void
  onRestart: () => void
}

/** State headline + progress bar, with the destructive action alongside. */
export function RunProgress({ job, busy, onStop, onRestart }: RunProgressProps) {
  const finished = job.status === JobStatus.FINISHED
  const failed = job.status === JobStatus.ERROR
  const live = job.is_live

  const total = job.nsteps !== null && job.nsteps !== undefined && job.nsteps > 0 ? job.nsteps : null
  const done = job.nsteps_done ?? null
  const known = total !== null && done !== null
  const percent = jobProgressPercent(job)

  let headline: React.ReactNode
  if (finished) {
    headline = "Finished"
  } else if (failed) {
    headline = "Failed"
  } else if (percent !== null) {
    headline = `${String(percent)}%`
  } else {
    headline = (
      <span className="inline-flex items-center gap-2">
        <LoaderCircle className="text-text-muted h-6 w-6 animate-spin" aria-hidden />
        Preparing
      </span>
    )
  }

  const tint = finished
    ? "[&_[data-slot=progress-indicator]]:bg-success"
    : failed
      ? "[&_[data-slot=progress-indicator]]:bg-error"
      : undefined

  return (
    <section aria-label="Run progress" className="space-y-3">
      <div className="grid items-center gap-3 sm:grid-cols-[1fr_auto_1fr]">
        <div className="hidden sm:block" />
        <div className="text-center">
          <p className="text-text-muted text-xs">Progress</p>
          <p className="flex items-center justify-center text-3xl font-semibold tracking-tight" aria-live="polite">
            {headline}
          </p>
        </div>
        <div className="justify-self-center sm:justify-self-end">
          {live ? (
            <Button
              type="button"
              variant="outline"
              className="border-error text-error hover:bg-error/10 hover:text-error"
              onClick={onStop}
              disabled={busy}
            >
              {busy ? <LoaderCircle className="animate-spin" aria-hidden /> : <Square aria-hidden />}
              Stop run
            </Button>
          ) : (
            <Button
              type="button"
              variant="outline"
              className="border-primary text-primary hover:bg-primary/10 hover:text-primary"
              onClick={onRestart}
              disabled={busy}
            >
              {busy ? <LoaderCircle className="animate-spin" aria-hidden /> : <RotateCcw aria-hidden />}
              Re-run
            </Button>
          )}
        </div>
      </div>

      {/* DS ≤ 0.1.9 Progress destructures `value` away from the Radix Root, so the
          determinate state never reaches AT — set aria-valuenow explicitly. */}
      <Progress
        value={finished ? 100 : (percent ?? 0)}
        aria-valuenow={finished ? 100 : (percent ?? 0)}
        className={tint}
        aria-label="Simulation progress"
      />

      <div className="space-y-1 text-center">
        {known && (
          <p className="text-text-muted text-sm tabular-nums">{`${(done as number).toLocaleString("en-US")} / ${(total as number).toLocaleString("en-US")} steps`}</p>
        )}
        {failed && <p className="text-text-muted text-sm">The run failed — check the logs below for details.</p>}
        {live && percent !== null && job.estimated_time !== null && job.estimated_time !== undefined && (
          <p className="text-text-muted inline-flex items-center gap-1 text-sm">
            <Clock className="h-3.5 w-3.5" aria-hidden />
            {`About ${formatTime(job.estimated_time)} remaining`}
          </p>
        )}
      </div>
    </section>
  )
}
