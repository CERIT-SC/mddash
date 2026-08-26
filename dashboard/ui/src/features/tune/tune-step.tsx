import { useEffect, useMemo, useRef, useState } from "react"

import { toApiError } from "@/api/errors"
import {
  getGetAmberJobQueryKey,
  getGetExperimentQueryKey,
  getGetGromacsJobQueryKey,
  getGetTunerJobQueryKey,
  getListSimulationsQueryKey,
  useDeleteTunerJob,
  useGetTunerJob,
  useStartTunerJob,
  useStopTunerJob,
  useSubmitAmberJob,
  useSubmitGromacsJob,
} from "@/api/generated/client"
import {
  Engine,
  JobStatus,
  type AmberJobRequest,
  type GromacsJobRequest,
  type Simulation,
  type TunerJob,
} from "@/api/generated/models"
import { ROLE_SPECS, type FileRoleKey } from "@/features/simulation"
import { ApiErrorAlert } from "@/shared/ui/api-error-alert"
import { HintTooltip } from "@/shared/ui/hint-tooltip"
import {
  Alert,
  AlertDescription,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertTitle,
  Button,
  buttonVariants,
  H4,
  Label,
  Separator,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@e-infra/design-system"
import { useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, Clock, LoaderCircle, Play, RotateCcw, Square } from "lucide-react"
import { toast } from "sonner"

import { CustomizeConfigSection } from "./customize-config"
import { HardwareConfigForm, type HardwareConfigValues } from "./hardware-config-form"
import { DEFAULT_NSTEPS, NstepsSelect } from "./nsteps-select"
import { toJobRequest } from "./run-request"
import { TrialLogDialog } from "./trial-log-dialog"
import { TrialsTable } from "./trials-table"
import { jobLive, parseTrials, type TrialRow } from "./tuned-trials"

type TuneMode = "tuning" | "manual"

type SubmitRunVars = { experimentId: string; simulationPath: string; data?: GromacsJobRequest | AmberJobRequest }
type SubmitRun = {
  mutate: (vars: SubmitRunVars, options?: { onSuccess?: () => void; onError?: (error: unknown) => void }) => void
  isPending: boolean
}

const TUNING_POLL_MS = 5000

/** File roles tuning requires on disk, per engine. Mirrors `require_files` in `tuner_job.py`. */
const TUNE_REQUIRED_ROLES: Record<Engine, FileRoleKey[]> = {
  [Engine.GMX]: ["run_input"],
  [Engine.AMBER]: ["topology", "coordinates", "control"],
}
// The footer submits whichever hardware form is active by native form id.
const MANUAL_FORM_ID = "tune-manual-config"
const CUSTOMIZE_FORM_ID = "tune-customize-config"

/** error_message is NullableString — treat both null and undefined as absent. */
const hasErrorMessage = (job: TunerJob) => job.error_message !== null && job.error_message !== undefined

type TuneStepProps = {
  experimentId: string
  engine: Engine
  simulation: Simulation
  /** URL-owned picked trial. */
  trialId: string | undefined
  /** URL-owned tab view. */
  mode: TuneMode
  onTrialIdChange: (trial: string | undefined) => void
  onModeChange: (mode: TuneMode) => void
  onStepChange: (step: number) => void
  /** Test seam; production callers omit it. */
  pollMs?: number
}

/** Tune wizard step: tune hardware configs (or enter one manually) and pick what the run uses. */
export function TuneStep({
  experimentId,
  engine,
  simulation,
  trialId,
  mode,
  onTrialIdChange,
  onModeChange,
  onStepChange,
  pollMs = TUNING_POLL_MS,
}: TuneStepProps) {
  const queryClient = useQueryClient()
  const [draftNsteps, setDraftNsteps] = useState(DEFAULT_NSTEPS)
  const [logTrialId, setLogTrialId] = useState<string | null>(null)
  const [confirmRetune, setConfirmRetune] = useState(false)
  const [confirmStartNsteps, setConfirmStartNsteps] = useState<number | null>(null)
  // The manual and customize forms never co-mount (separate tabs), so one flag suffices.
  const [formValid, setFormValid] = useState(false)

  const jobQuery = useGetTunerJob(experimentId, simulation.simulation_path, {
    query: {
      retry: false,
      // Poll only while the job is alive; stopped/finished results are static.
      refetchInterval: (query) => {
        // A gone job is terminal even though TanStack keeps the last 200 as stale data.
        if ((query.state.error as { status?: number } | null)?.status === 404) return false
        const data = query.state.data
        return data?.status === 200 && !hasErrorMessage(data.data) && jobLive(data.data) ? pollMs : false
      },
    },
  })
  // A 404 means "no job", even with the previous 200 kept as stale data.
  const missing = jobQuery.error?.status === 404
  const job = !missing && jobQuery.data?.status === 200 ? jobQuery.data.data : undefined
  const live = job !== undefined && !hasErrorMessage(job) && jobLive(job)
  const rows = useMemo(() => (job === undefined ? [] : parseTrials(engine, job.trials)), [engine, job])

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: getGetTunerJobQueryKey(experimentId, simulation.simulation_path) })
    void queryClient.invalidateQueries({ queryKey: getListSimulationsQueryKey(experimentId) })
    void queryClient.invalidateQueries({ queryKey: getGetExperimentQueryKey(experimentId) })
  }

  const start = useStartTunerJob({
    mutation: {
      onSuccess: () => {
        toast.success("Tuning started")
        invalidate()
      },
      onError: (error) => toast.error(toApiError(error).message),
    },
  })
  const stop = useStopTunerJob({
    mutation: {
      onSuccess: () => {
        toast.success("Tuning stopped — results so far are kept")
        invalidate()
      },
      onError: (error) => toast.error(toApiError(error).message),
    },
  })
  const retune = useDeleteTunerJob({
    mutation: {
      onSuccess: () => {
        setConfirmRetune(false)
        onTrialIdChange(undefined)
        invalidate()
      },
      onError: (error) => toast.error(toApiError(error).message),
    },
  })

  // The Run Simulation footer submits the production job, then navigates to Run.
  // Engine-picked hook pair; the request body matches the engine via toJobRequest.
  const gmxSubmit = useSubmitGromacsJob()
  const amberSubmit = useSubmitAmberJob()
  const submitRun = (engine === Engine.AMBER ? amberSubmit : gmxSubmit) as unknown as SubmitRun

  // Run Simulation submits the production job and navigates to Run on success;
  // a failure stays on Tune with the actionable error.
  const startRun = (values: HardwareConfigValues) =>
    submitRun.mutate(
      { experimentId, simulationPath: simulation.simulation_path, data: toJobRequest(engine, values) },
      {
        onSuccess: () => {
          toast.success("Run started")
          const jobKey =
            engine === Engine.AMBER
              ? getGetAmberJobQueryKey(experimentId, simulation.simulation_path)
              : getGetGromacsJobQueryKey(experimentId, simulation.simulation_path)
          void queryClient.invalidateQueries({ queryKey: jobKey })
          void queryClient.invalidateQueries({ queryKey: getListSimulationsQueryKey(experimentId) })
          void queryClient.invalidateQueries({ queryKey: getGetExperimentQueryKey(experimentId) })
          onStepChange(2)
        },
        onError: (error) => toast.error(toApiError(error).message),
      }
    )

  // The pick counts only while THIS job contains it (tab switches carry the URL over).
  const pickedRow = useMemo(
    () => (trialId === undefined ? undefined : rows.find((row) => row.id === trialId)),
    [trialId, rows]
  )

  const startJob = (nsteps: number) => {
    onTrialIdChange(undefined)
    start.mutate({ experimentId, data: { simulation_path: simulation.simulation_path, nsteps } })
  }

  const picked = pickedRow !== undefined

  // Clear a stale pick: job deleted (404) or trial no longer present. `missing`
  // flips only after a resolved fetch, so a reloaded page never clears mid-load.
  useEffect(() => {
    if (trialId === undefined) return
    if (missing || (job !== undefined && !rows.some((row) => row.id === trialId))) {
      onTrialIdChange(undefined)
    }
  }, [trialId, missing, job, rows, onTrialIdChange])

  // UNKNOWN + no trials = no poll ever succeeded (API falls back to empty status when the tuner is
  // down). Structural sharing keeps data identical across polls, so dataUpdatedAt is the tick.
  const silent = live && job?.tuner_status === JobStatus.UNKNOWN && job?.trials.length === 0
  const silentStart = useRef<number | null>(null)
  const [tunerSilent, setTunerSilent] = useState(false)
  useEffect(() => {
    if (!silent) {
      silentStart.current = null
      setTunerSilent(false)
      return
    }
    silentStart.current ??= Date.now()
    if (Date.now() - silentStart.current > 4 * pollMs) setTunerSilent(true)
  }, [silent, pollMs, jobQuery.dataUpdatedAt])

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <H4>Tune your simulation</H4>
        <p className="text-text-muted text-sm">
          Tuning runs your simulation briefly across different hardware settings to find the fastest one.
        </p>
      </div>

      <Tabs value={mode} onValueChange={(next) => onModeChange(next as TuneMode)}>
        <TabsList aria-label="Configuration method">
          <TabsTrigger value="tuning">Tuning</TabsTrigger>
          <TabsTrigger value="manual">Manual configuration</TabsTrigger>
        </TabsList>

        <TabsContent value="tuning" className="space-y-6 pt-4">
          <TuningBody
            simulation={simulation}
            job={job}
            live={live}
            tunerSilent={tunerSilent}
            rows={rows}
            pending={jobQuery.isPending}
            error={missing ? undefined : jobQuery.isError ? jobQuery.error : undefined}
            onRetry={() => void jobQuery.refetch()}
            startPending={start.isPending}
            stopPending={stop.isPending}
            draftNsteps={draftNsteps}
            onDraftNstepsChange={setDraftNsteps}
            onStart={setConfirmStartNsteps}
            onStop={() => stop.mutate({ experimentId, simulationPath: simulation.simulation_path })}
            onRetune={() => setConfirmRetune(true)}
            trialId={trialId}
            onTrialIdChange={onTrialIdChange}
            onShowLogs={setLogTrialId}
            engine={engine}
          />
          {pickedRow !== undefined && (
            <CustomizeConfigSection
              engine={engine}
              row={pickedRow}
              formId={CUSTOMIZE_FORM_ID}
              onSubmit={startRun}
              onValidityChange={setFormValid}
            />
          )}
        </TabsContent>

        <TabsContent value="manual" className="space-y-6 pt-4">
          <div className="space-y-5">
            <p className="text-text-muted text-xs font-semibold tracking-wide uppercase">Enter custom configuration</p>
            <HardwareConfigForm
              engine={engine}
              formId={MANUAL_FORM_ID}
              onSubmit={startRun}
              onValidityChange={setFormValid}
            />
          </div>
        </TabsContent>
      </Tabs>

      <Separator />

      <div className="flex items-center justify-between">
        <Button type="button" variant="outline" onClick={() => onStepChange(0)}>
          <ArrowLeft aria-hidden />
          Back
        </Button>
        {/* One submit button for whichever hardware form is active; validity
            (and, in tuning mode, a real pick) gates the submit. */}
        <Button
          type="submit"
          form={mode === "manual" ? MANUAL_FORM_ID : CUSTOMIZE_FORM_ID}
          disabled={submitRun.isPending || (mode === "manual" ? !formValid : !(picked && formValid))}
        >
          {submitRun.isPending ? <LoaderCircle className="animate-spin" aria-hidden /> : <Play aria-hidden />}
          Run Simulation
        </Button>
      </div>

      {/* AlertDialogAction has no variant prop in DS ≤ 0.1.9 — buttonVariants workaround
          until https://github.com/CERIT-SC/design-system/pull/108 lands. */}
      <AlertDialog open={confirmRetune} onOpenChange={setConfirmRetune}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Discard tuning results?</AlertDialogTitle>
            <AlertDialogDescription>
              Re-tuning deletes the current results for this simulation and starts over. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep results</AlertDialogCancel>
            <AlertDialogAction
              className={buttonVariants({ variant: "error" })}
              onClick={() => retune.mutate({ experimentId, simulationPath: simulation.simulation_path })}
            >
              Re-tune
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={confirmStartNsteps !== null} onOpenChange={(open) => !open && setConfirmStartNsteps(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Clock className="text-primary" aria-hidden />
              Start tuning with {confirmStartNsteps?.toLocaleString("en-US")} steps?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Tuning at this size usually takes <strong>several minutes</strong>. You can close the page — it keeps
              running, and you can stop it from this step.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => confirmStartNsteps !== null && startJob(confirmStartNsteps)}>
              <Play aria-hidden />
              Start tuning
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <TrialLogDialog
        experimentId={experimentId}
        simulationPath={simulation.simulation_path}
        trialId={logTrialId}
        onClose={() => setLogTrialId(null)}
      />
    </div>
  )
}

type TuningBodyProps = {
  simulation: Simulation
  job: TunerJob | undefined
  live: boolean
  tunerSilent: boolean
  rows: TrialRow[]
  pending: boolean
  error: unknown
  onRetry: () => void
  startPending: boolean
  stopPending: boolean
  draftNsteps: number
  onDraftNstepsChange: (nsteps: number) => void
  onStart: (nsteps: number) => void
  onStop: () => void
  onRetune: () => void
  trialId: string | undefined
  onTrialIdChange: (trial: string | undefined) => void
  onShowLogs: (trial: string) => void
  engine: Engine
}

function TuningBody({
  simulation,
  job,
  live,
  tunerSilent,
  rows,
  pending,
  error,
  onRetry,
  startPending,
  stopPending,
  draftNsteps,
  onDraftNstepsChange,
  onStart,
  onStop,
  onRetune,
  trialId,
  onTrialIdChange,
  onShowLogs,
  engine,
}: TuningBodyProps) {
  if (pending && job === undefined) {
    return (
      <div className="space-y-4" aria-label="Loading tuner job">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-10 w-40" />
      </div>
    )
  }

  if (error !== undefined) {
    return <ApiErrorAlert error={error} onRetry={onRetry} />
  }

  if (job === undefined) {
    const blockers: string[] = []
    if (!simulation.valid) blockers.push("The simulation manifest is invalid.")
    const missingRequired = TUNE_REQUIRED_ROLES[engine].filter(
      (role) => !simulation.files[role] || simulation.missing_files.includes(role)
    )
    if (missingRequired.length > 0) {
      const labels = missingRequired.map((role) => ROLE_SPECS[engine].find((spec) => spec.key === role)?.label ?? role)
      blockers.push(`Missing files: ${labels.join(", ")}.`)
    }
    return (
      <div className="space-y-4">
        {blockers.length > 0 && (
          <Alert variant="warning">
            <AlertTitle>Finish setup first</AlertTitle>
            <AlertDescription>
              {blockers.join(" ")} Go back to the Setup step to fix this before tuning.
            </AlertDescription>
          </Alert>
        )}
        <div className="flex flex-wrap items-end gap-4">
          <NstepsField id="tune-nsteps-idle" value={draftNsteps} onValueChange={onDraftNstepsChange} />
          <Button type="button" onClick={() => onStart(draftNsteps)} disabled={startPending || blockers.length > 0}>
            {startPending ? <LoaderCircle className="animate-spin" aria-hidden /> : <Play aria-hidden />}
            Start tuning
          </Button>
        </div>
      </div>
    )
  }

  if (hasErrorMessage(job)) {
    return (
      <div className="space-y-4">
        <Alert variant="error">
          <AlertTitle>Tuning failed</AlertTitle>
          <AlertDescription>{job.error_message}</AlertDescription>
        </Alert>
        <Button type="button" onClick={() => onStart(job.nsteps)} disabled={startPending}>
          {startPending ? <LoaderCircle className="animate-spin" aria-hidden /> : <RotateCcw aria-hidden />}
          Tune again
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-4">
        {/* The displayed nsteps is the job's — changing it requires a re-tune. */}
        <NstepsField id="tune-nsteps-job" value={job.nsteps} onValueChange={() => undefined} disabled />
        {live ? (
          <Button
            type="button"
            variant="outline"
            className="border-error text-error hover:bg-error/10 hover:text-error"
            onClick={onStop}
            disabled={stopPending}
          >
            {stopPending ? <LoaderCircle className="animate-spin" aria-hidden /> : <Square aria-hidden />}
            Stop tuning
          </Button>
        ) : (
          <Button type="button" variant="ghost" onClick={onRetune}>
            <RotateCcw aria-hidden />
            Re-tune
          </Button>
        )}
      </div>

      {tunerSilent && (
        <Alert variant="warning">
          <AlertTitle>The tuner is not responding</AlertTitle>
          <AlertDescription>
            No trial results have arrived and the tuning service is not answering status checks. Tuning keeps retrying
            on its own; you can also stop the job and try again later.
          </AlertDescription>
        </Alert>
      )}

      <p className="text-sm font-semibold">Pick a configuration</p>
      <TrialsTable
        engine={engine}
        rows={rows}
        value={trialId}
        onValueChange={onTrialIdChange}
        live={live}
        onShowLogs={onShowLogs}
      />
    </div>
  )
}

type NstepsFieldProps = {
  id: string
  value: number
  onValueChange: (nsteps: number) => void
  disabled?: boolean
}

function NstepsField({ id, value, onValueChange, disabled = false }: NstepsFieldProps) {
  return (
    <div className="space-y-2">
      {/* Hint stays outside the Label — inside, it would leak into the control's accessible name. */}
      <span className="inline-flex items-center gap-1">
        <Label htmlFor={id}>Number of steps</Label>
        <HintTooltip text="Length of each tuning trial in MD steps. Longer trials give more reliable estimates but take longer." />
      </span>
      <NstepsSelect id={id} value={value} onValueChange={onValueChange} disabled={disabled} />
    </div>
  )
}
