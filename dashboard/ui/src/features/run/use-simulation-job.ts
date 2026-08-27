import {
  useDeleteAmberJob,
  useDeleteGromacsJob,
  useGetAmberJob,
  useGetAmberJobLog,
  useGetGromacsJob,
  useGetGromacsJobLog,
  useSubmitAmberJob,
  useSubmitGromacsJob,
} from "@/api/generated/client"
import {
  Engine,
  type AmberJob,
  type AmberJobRequest,
  type GromacsJob,
  type GromacsJobRequest,
  type SimulationJob,
} from "@/api/generated/models"
import { toJobRequest } from "@/features/tune"

/** Whole-percent progress; null while either step count is unknown. */
export function jobProgressPercent(job: SimulationJob): number | null {
  if (job.nsteps === null || job.nsteps === undefined || job.nsteps <= 0) return null
  if (job.nsteps_done === null || job.nsteps_done === undefined) return null
  return Math.min(100, Math.round((job.nsteps_done / job.nsteps) * 100))
}

/** Engine log stream key used by the log endpoint (`?type=`). */
export function engineLogType(engine: Engine): "gmx" | "mdout" {
  return engine === Engine.AMBER ? "mdout" : "gmx"
}

/** Rebuild the submit request from an existing job (used by Re-run). */
export function jobConfigRequest(engine: Engine, job: SimulationJob): GromacsJobRequest | AmberJobRequest {
  // Job fields are non-nullable server-side; only the engine→field mapping
  // (shared with the submit path via toJobRequest) happens here.
  const picks =
    engine === Engine.AMBER
      ? { pickA: (job as AmberJob).binary, pickB: (job as AmberJob).ewald }
      : { pickA: (job as GromacsJob).pme, pickB: (job as GromacsJob).nb }
  return toJobRequest(engine, { ...picks, np: job.np, ntomp: job.ntomp })
}

// The generated hooks come in engine pairs; each wrapper mounts both but enables
// only the engine's own, then hands the active one to the caller.

const pollWhileLive =
  (pollMs: number) =>
  (query: { state: { error: unknown; data: unknown } }): number | false => {
    // A 404 means "no job", even with the previous 200 kept as stale data.
    if ((query.state.error as { status?: number } | null)?.status === 404) return false
    // Anything other than a live 200 (terminal states, other errors) stops the poll.
    const data = query.state.data as { status: number; data: SimulationJob } | undefined
    return data?.status === 200 && data.data.is_live ? pollMs : false
  }

export type SimulationJobQuery = {
  /** Present only on a resolved 200; stays undefined on 404 ("no job"). */
  job: GromacsJob | AmberJob | undefined
  /** Resolved 404 — there is no job for this simulation. */
  missing: boolean
  pending: boolean
  /** Non-404 query failure. */
  error: unknown
  retry: () => void
}

export function useSimulationJobQuery(
  experimentId: string,
  simulationPath: string,
  engine: Engine,
  pollMs: number
): SimulationJobQuery {
  const gmx = useGetGromacsJob(experimentId, simulationPath, {
    query: { retry: false, enabled: engine !== Engine.AMBER, refetchInterval: pollWhileLive(pollMs) },
  })
  const amber = useGetAmberJob(experimentId, simulationPath, {
    query: { retry: false, enabled: engine === Engine.AMBER, refetchInterval: pollWhileLive(pollMs) },
  })
  const active = engine === Engine.AMBER ? amber : gmx
  const missing = (active.error as { status?: number } | null)?.status === 404
  const job = !missing && active.data?.status === 200 ? active.data.data : undefined
  return {
    job,
    missing,
    pending: active.isPending,
    error: active.isError && !missing ? active.error : undefined,
    retry: () => void active.refetch(),
  }
}

type SubmitVars = { experimentId: string; simulationPath: string; data?: GromacsJobRequest | AmberJobRequest }
type DeleteVars = { experimentId: string; simulationPath: string }

type JobMutation<Vars> = {
  mutate: (
    vars: Vars,
    options?: { onSuccess?: () => void; onError?: (error: unknown) => void; onSettled?: () => void }
  ) => void
  isPending: boolean
}

export type JobMutations = {
  submit: JobMutation<SubmitVars>
  remove: JobMutation<DeleteVars>
}

/**
 * Engine-picked submit/delete. The union cast is sound: callers pair the GMX
 * request body with engine GMX (and AMBER with AMBER) via toJobRequest /
 * jobConfigRequest.
 */
export function useJobMutations(engine: Engine): JobMutations {
  const gmxSubmit = useSubmitGromacsJob()
  const amberSubmit = useSubmitAmberJob()
  const gmxDelete = useDeleteGromacsJob()
  const amberDelete = useDeleteAmberJob()
  const submit = engine === Engine.AMBER ? amberSubmit : gmxSubmit
  const remove = engine === Engine.AMBER ? amberDelete : gmxDelete
  return {
    submit: { mutate: submit.mutate as unknown as JobMutation<SubmitVars>["mutate"], isPending: submit.isPending },
    remove: { mutate: remove.mutate as unknown as JobMutation<DeleteVars>["mutate"], isPending: remove.isPending },
  }
}

/** Matches the server default window; longer logs show a truncation note. */
export const LOG_TAIL = 10000

export type SimulationJobLog = {
  /** Fetched window; undefined while loading or on 404. */
  text: string | undefined
  /** The stream's file does not exist yet. */
  missing: boolean
  pending: boolean
  /** Non-404 fetch failure. */
  failed: boolean
}

export function useSimulationJobLog(
  experimentId: string,
  simulationPath: string,
  engine: Engine,
  type: string,
  options: { enabled: boolean; live: boolean; pollMs: number }
): SimulationJobLog {
  const gmx = useGetGromacsJobLog(
    experimentId,
    simulationPath,
    { type, tail: LOG_TAIL },
    {
      query: {
        retry: false,
        enabled: engine !== Engine.AMBER && options.enabled,
        refetchInterval: options.live ? options.pollMs : false,
      },
    }
  )
  const amber = useGetAmberJobLog(
    experimentId,
    simulationPath,
    { type, tail: LOG_TAIL },
    {
      query: {
        retry: false,
        enabled: engine === Engine.AMBER && options.enabled,
        refetchInterval: options.live ? options.pollMs : false,
      },
    }
  )
  const active = engine === Engine.AMBER ? amber : gmx
  const missing = (active.error as { status?: number } | null)?.status === 404
  return {
    text: !missing && active.data?.status === 200 ? active.data.data : undefined,
    missing,
    pending: active.isPending,
    failed: active.isError && !missing,
  }
}
