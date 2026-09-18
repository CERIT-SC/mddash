import { useListAmberJobs, useListGromacsJobs } from "@/api/generated/client"
import { Engine, type AmberJob, type GromacsJob } from "@/api/generated/models"
import { JOB_STATUS_LABEL } from "@/shared/job-status"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@e-infra/design-system"

type SegmentsListProps = {
  experimentId: string
  simulationPath: string
  engine: Engine
  /** While the active segment is live, the list re-polls on this interval. */
  live?: boolean
  pollMs?: number
}

type Segment = GromacsJob | AmberJob

function formatTimestamp(ts: number | null | undefined): string {
  if (ts === null || ts === undefined) return "—"
  return new Date(ts * 1000).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function formatSteps(job: Segment): string {
  if (job.nsteps === null || job.nsteps === undefined) return "—"
  if (job.nsteps_done === null || job.nsteps_done === undefined) return `— / ${job.nsteps.toLocaleString("en-US")}`
  return `${job.nsteps_done.toLocaleString("en-US")} / ${job.nsteps.toLocaleString("en-US")}`
}

/**
 * One row per run segment: the initial run plus every extension. The trajectory
 * itself stays append-continuous; this lists the submission history behind it.
 */
export function SegmentsList({ experimentId, simulationPath, engine, live, pollMs = 5000 }: SegmentsListProps) {
  const refetchInterval = live ? pollMs : false
  const gmx = useListGromacsJobs(experimentId, {
    query: { retry: false, enabled: engine !== Engine.AMBER, refetchInterval },
  })
  const amber = useListAmberJobs(experimentId, {
    query: { retry: false, enabled: engine === Engine.AMBER, refetchInterval },
  })
  const active = engine === Engine.AMBER ? amber : gmx

  const jobs: Segment[] = (active.data?.status === 200 ? active.data.data : [])
    .filter((job: Segment) => job.simulation_path === simulationPath)
    .sort((a: Segment, b: Segment) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())

  if (active.isPending || jobs.length === 0) return null

  return (
    <section aria-label="Run history" className="space-y-2">
      <p className="text-text-muted text-sm font-medium">Run history</p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Segment</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Steps</TableHead>
            <TableHead>ns/day</TableHead>
            <TableHead>Started</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs.map((job, index) => (
            <TableRow key={job.id}>
              <TableCell>{index + 1}</TableCell>
              <TableCell>{JOB_STATUS_LABEL[job.status]}</TableCell>
              <TableCell className="tabular-nums">{formatSteps(job)}</TableCell>
              <TableCell className="tabular-nums">{job.performance ?? "—"}</TableCell>
              <TableCell>{formatTimestamp(job.start_timestamp)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  )
}
