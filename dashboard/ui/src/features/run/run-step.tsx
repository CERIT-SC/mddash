import { useEffect, useMemo, useState } from "react"

import { toApiError } from "@/api/errors"
import {
  getGetAmberJobQueryKey,
  getGetExperimentQueryKey,
  getGetGromacsJobQueryKey,
  getListSimulationsQueryKey,
  useGetTunerJob,
} from "@/api/generated/client"
import { Engine, JobStatus, type Simulation } from "@/api/generated/models"
import { parseTrials } from "@/features/tune"
import { ApiErrorAlert } from "@/shared/ui/api-error-alert"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
  buttonVariants,
  H4,
  Separator,
  Skeleton,
} from "@e-infra/design-system"
import { useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, ArrowRight, RotateCcw, Square } from "lucide-react"
import { toast } from "sonner"

import { ConfigUsed } from "./config-used"
import { RunLogs } from "./run-logs"
import { RunProgress } from "./run-progress"
import { jobConfigRequest, useJobMutations, useSimulationJobQuery } from "./use-simulation-job"

const RUN_POLL_MS = 5000

type RunStepProps = {
  experimentId: string
  engine: Engine
  simulation: Simulation
  onStepChange: (step: number) => void
  /** Test seam; production callers omit it. */
  pollMs?: number
}

/** Run wizard step: submit, watch, stop, or re-run the production simulation. */
export function RunStep({ experimentId, engine, simulation, onStepChange, pollMs = RUN_POLL_MS }: RunStepProps) {
  const queryClient = useQueryClient()
  const [confirmStop, setConfirmStop] = useState(false)
  const [confirmRestart, setConfirmRestart] = useState(false)
  // Suppresses the gone-job auto-navigation during the re-run delete→submit chain.
  const [restarting, setRestarting] = useState(false)

  const jobQuery = useSimulationJobQuery(experimentId, simulation.simulation_path, engine, pollMs)
  const job = jobQuery.job
  const live = job !== undefined && job.is_live
  const failed = job?.status === JobStatus.ERROR

  // Tuner trials power the config table's estimates; a 404 just means "no tuning".
  const tunerQuery = useGetTunerJob(experimentId, simulation.simulation_path, { query: { retry: false } })
  const tunerJob = tunerQuery.data?.status === 200 ? tunerQuery.data.data : undefined
  const trials = useMemo(() => (tunerJob === undefined ? [] : parseTrials(engine, tunerJob.trials)), [engine, tunerJob])

  const invalidate = () => {
    const jobKey =
      engine === Engine.AMBER
        ? getGetAmberJobQueryKey(experimentId, simulation.simulation_path)
        : getGetGromacsJobQueryKey(experimentId, simulation.simulation_path)
    void queryClient.invalidateQueries({ queryKey: jobKey })
    void queryClient.invalidateQueries({ queryKey: getListSimulationsQueryKey(experimentId) })
    void queryClient.invalidateQueries({ queryKey: getGetExperimentQueryKey(experimentId) })
  }

  const mutations = useJobMutations(engine)
  const stopping = mutations.remove.isPending && !restarting
  const busy = mutations.remove.isPending || mutations.submit.isPending

  const vars = { experimentId, simulationPath: simulation.simulation_path }

  const stopRun = () =>
    mutations.remove.mutate(vars, {
      onSuccess: () => {
        setConfirmStop(false)
        toast.success("Run stopped")
        invalidate()
      },
      onError: (error) => toast.error(toApiError(error).message),
    })

  const restartRun = () => {
    if (job === undefined) return
    setRestarting(true)
    mutations.remove.mutate(vars, {
      onSuccess: () => {
        mutations.submit.mutate(
          { ...vars, data: jobConfigRequest(engine, job) },
          {
            onSuccess: () => {
              toast.success("Run restarted")
              invalidate()
            },
            onError: (error) => toast.error(toApiError(error).message),
            onSettled: () => {
              setConfirmRestart(false)
              setRestarting(false)
            },
          }
        )
      },
      onError: (error) => {
        toast.error(toApiError(error).message)
        setConfirmRestart(false)
        setRestarting(false)
      },
    })
  }

  // A gone job (deleted here or elsewhere) means this step has nothing to show —
  // the run lifecycle restarts from Tune, so send the user there.
  const missing = jobQuery.missing
  useEffect(() => {
    if (missing && !restarting) onStepChange(1)
  }, [missing, restarting, onStepChange])

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <H4>Run your simulation</H4>
        <p className="text-text-muted text-sm">
          This step runs your full simulation with the configuration below. It can take a while — you'll be able to
          leave the page and come back to check progress.
        </p>
      </div>

      {job === undefined && jobQuery.pending ? (
        <div className="space-y-4" aria-label="Loading simulation job">
          <Skeleton className="h-10 w-72" />
          <Skeleton className="h-10 w-40" />
        </div>
      ) : jobQuery.error !== undefined ? (
        <ApiErrorAlert error={jobQuery.error} onRetry={jobQuery.retry} />
      ) : job === undefined ? (
        <p className="text-text-muted text-sm">No run in progress — taking you back to tuning…</p>
      ) : (
        <div className="space-y-6">
          <ConfigUsed engine={engine} job={job} trials={trials} />
          <RunProgress
            job={job}
            busy={busy}
            onStop={() => setConfirmStop(true)}
            onRestart={() => setConfirmRestart(true)}
          />
          {/* A pending pod has produced nothing — every stream 404s, so there is
              nothing to show and no reason to hit the log endpoint. */}
          {job.status !== JobStatus.PENDING && (
            <RunLogs
              experimentId={experimentId}
              simulationPath={simulation.simulation_path}
              engine={engine}
              logLines={job.log_lines}
              live={live}
              failed={failed}
              pollMs={pollMs}
            />
          )}
        </div>
      )}

      <Separator />

      <div className="flex items-center justify-end gap-2">
        <Button type="button" variant="outline" onClick={() => onStepChange(1)}>
          <ArrowLeft aria-hidden />
          Back
        </Button>
        <Button type="button" disabled={job?.status !== JobStatus.FINISHED} onClick={() => onStepChange(3)}>
          Analyze
          <ArrowRight aria-hidden />
        </Button>
      </div>

      {/* AlertDialogAction has no variant prop in DS ≤ 0.1.9 — buttonVariants workaround
          until https://github.com/CERIT-SC/design-system/pull/108 lands. */}
      <AlertDialog open={confirmStop} onOpenChange={setConfirmStop}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Square className="text-error" aria-hidden />
              Stop this run?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Stopping deletes the run, its progress so far, and its logs. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep running</AlertDialogCancel>
            <AlertDialogAction className={buttonVariants({ variant: "error" })} onClick={stopRun} disabled={stopping}>
              <Square aria-hidden />
              Stop run
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={confirmRestart} onOpenChange={setConfirmRestart}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <RotateCcw className="text-primary" aria-hidden />
              Re-run the simulation?
            </AlertDialogTitle>
            <AlertDialogDescription>
              The current results and logs will be deleted, and the run starts again with the same configuration. This
              cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={restartRun} disabled={restarting}>
              <RotateCcw aria-hidden />
              Re-run
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
