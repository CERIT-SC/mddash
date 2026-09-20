import { useEffect, useRef, useState } from "react"

import { toApiError } from "@/api/errors"
import {
  getListExperimentsQueryKey,
  useArchiveExperiment,
  useDeleteExperiment,
  useGetArchiveStatus,
  useListAnalysisResults,
  useListAnalysisTypes,
  useRestoreExperiment,
  useStartNotebook,
  useStopNotebook,
  useUpdateExperiment,
} from "@/api/generated/client"
import type { Experiment } from "@/api/generated/models"
import { getAnalysisLabel } from "@/features/analyze"
import {
  isNotebookQuotaError,
  NotebookQuotaDialog,
  useNotebookQuota,
  type PendingNotebookStart,
} from "@/features/notebook"
import { ENGINE_LABELS } from "@/shared/engine"
import { formatBytes, formatTime, relativeTime } from "@/shared/format"
import { ModuleIconTile } from "@/shared/module-icon"
import { isNotebookActive } from "@/shared/pod-status"
import { sourceLabel } from "@/shared/source"
import { InfoBanner } from "@/shared/ui/info-banner"
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
  Card,
  CardAction,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
  cn,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Input,
  Label,
  List,
} from "@e-infra/design-system"
import { useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { Archive, Copy, Database, Ellipsis, LoaderCircle, Pencil, Play, Square, Trash2, Undo2 } from "lucide-react"
import { toast } from "sonner"

import { archiveReasonLabel, archiveStateLabel, isArchived, isArchivedFailed, isArchiving } from "./archive"
import { isAnalysisJobLive } from "./live-work"

const STEP_LABELS = ["Setup", "Tune", "Run", "Analyze", "Publish"] as const

// The API step IS the phase index (Setup 0 .. Analyze 3, publish states 4) and
// is consumed directly; the shown counter counts from 1.
function stepParts(experiment: Experiment): { shownStep: number; stepIndex: number } {
  const step = Math.max(0, Math.min(experiment.step ?? 0, STEP_LABELS.length - 1))
  return { shownStep: step + 1, stepIndex: step }
}

function subtitle(experiment: Experiment): string {
  return `${experiment.module_name ?? "Custom"} · ${ENGINE_LABELS[experiment.engine]}`
}

// Jobs decide the label, not the status string: a publish draft masks running
// work, and "analyzing" outlives the last analysis job.
const latest = <T extends { created_at: string }>(jobs: T[]) =>
  jobs.reduce<T | undefined>((best, job) => (!best || job.created_at > best.created_at ? job : best), undefined)

// A running analysis outranks the simulating phase: it is the shorter job,
// so the card flips back to the simulation's percentage once it settles.
function liveLabel(experiment: Experiment): string | null {
  const analysis = latest(experiment.analysis_jobs.filter(isAnalysisJobLive))
  if (analysis) return `Analyzing ${getAnalysisLabel(analysis.analysis_name)}`
  if (experiment.simulation_jobs.some((job) => job.is_live)) {
    // Queued jobs have no log yet; steps-done defaults to 0%.
    const job =
      experiment.simulation_jobs.find((candidate) => candidate.status === "RUNNING") ??
      latest(experiment.simulation_jobs.filter((candidate) => candidate.is_live))
    const nsteps = job?.nsteps
    return nsteps ? `Simulating · ${Math.round(((job?.nsteps_done ?? 0) / nsteps) * 100)}%` : "Simulating"
  }
  if (experiment.tuner_jobs.some((job) => job.is_live)) return "Tuning"
  return null
}

type DetailRowProps = { label: string; value: string }

function DetailRow({ label, value }: DetailRowProps) {
  return (
    <div className="flex items-baseline justify-between gap-4 text-sm">
      <dt className="text-text-muted">{label}</dt>
      <dd className={value === "N/A" ? "text-text-muted" : undefined}>{value}</dd>
    </div>
  )
}

type DetailsProps = { experiment: Experiment }

function SetupDetails({ experiment }: DetailsProps) {
  // Index 0 is only ever paired with status "setup" (backend tuple invariant),
  // so setup is by definition not ready on this card.
  return (
    <>
      <DetailRow label="Setup ready" value="No" />
      <DetailRow label="Workflow" value={experiment.module_name ?? "Custom"} />
    </>
  )
}

function TuneDetails({ experiment }: DetailsProps) {
  const tuner = latest(experiment.tuner_jobs)
  const explored =
    tuner?.trials.filter((trial) => trial.performance !== null && trial.performance !== undefined).length ?? 0
  return (
    <>
      <DetailRow label="Configurations" value={tuner ? `${explored} of ${tuner.trials.length} explored` : "N/A"} />
      <DetailRow label="Steps" value={tuner ? tuner.nsteps.toLocaleString() : "N/A"} />
    </>
  )
}

function RunDetails({ experiment }: DetailsProps) {
  const job = latest(experiment.simulation_jobs)
  const remaining = typeof job?.estimated_time === "number" && job.estimated_time > 0 ? job.estimated_time : null
  return (
    <>
      <DetailRow label="Time remaining" value={remaining === null ? "N/A" : formatTime(remaining)} />
      <DetailRow label="Steps" value={job?.nsteps ? job.nsteps.toLocaleString() : "N/A"} />
    </>
  )
}

// The experiment has no global status: it always inherits the latest simulation's
// step/status, so analysis rows are scoped to that simulation.
function AnalyzeDetails({ experiment }: DetailsProps) {
  const simulationPath = experiment.latest_simulation_path ?? ""
  // Jobs ride the polled experiments list, so no separate query goes stale.
  const jobs = experiment.analysis_jobs.filter((job) => job.simulation_path === simulationPath)
  const analyzing = jobs.some(isAnalysisJobLive)
  const models = useListAnalysisResults(
    experiment.id,
    { simulation_path: simulationPath },
    {
      query: { enabled: simulationPath !== "", retry: false },
    }
  )
  // The pool is the hard MDDB workflow set, not the jobs submitted so far. It is
  // experiment-independent, so it needs no simulation_path gate and never goes stale.
  const types = useListAnalysisTypes(experiment.id, { query: { retry: false, staleTime: Number.POSITIVE_INFINITY } })

  // Results land when a calculation settles; refetch the Models count on that edge.
  const wasAnalyzing = useRef(false)
  const refetchModels = models.refetch
  useEffect(() => {
    if (wasAnalyzing.current && !analyzing) void refetchModels()
    wasAnalyzing.current = analyzing
  }, [analyzing, refetchModels])

  if (!simulationPath) {
    return (
      <>
        <DetailRow label="Models" value="N/A" />
        <DetailRow label="Analyses" value="N/A" />
      </>
    )
  }

  const ready = jobs.filter((job) => job.status === "FINISHED").length
  const total = types.data?.status === 200 ? types.data.data.length : undefined
  return (
    <>
      <DetailRow label="Models" value={models.data?.status === 200 ? String(models.data.data.length) : "…"} />
      <DetailRow label="Analyses" value={total === undefined ? "…" : `${ready} of ${total} ready`} />
    </>
  )
}

function PublishDetails({ experiment }: DetailsProps) {
  return (
    <>
      <DetailRow label="Published" value={experiment.mdrepo_published ? "Yes" : "No"} />
      {/* The only publish target so far is InvenioRDM-based MDRepo (no MDPosit publishing yet). */}
      <DetailRow label="Target" value={experiment.mdrepo_id ? "Invenio / MDRepo" : "N/A"} />
    </>
  )
}

const STEP_DETAILS = [SetupDetails, TuneDetails, RunDetails, AnalyzeDetails, PublishDetails] as const

function StepDetails({ experiment, stepIndex }: { experiment: Experiment; stepIndex: number }) {
  const Details = STEP_DETAILS[stepIndex]
  return (
    <dl className="border-border space-y-2 border-t pt-4">
      <Details experiment={experiment} />
    </dl>
  )
}

type ExperimentCardProps = { experiment: Experiment }

function activeJobCount(experiment: Experiment): number {
  return (
    experiment.simulation_jobs.filter((job) => job.is_live).length +
    experiment.tuner_jobs.filter((job) => job.is_live).length +
    experiment.analysis_jobs.filter(isAnalysisJobLive).length
  )
}

export function ExperimentCard({ experiment }: ExperimentCardProps) {
  const queryClient = useQueryClient()
  const [renameOpen, setRenameOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [restoreOpen, setRestoreOpen] = useState(false)
  const [quotaOpen, setQuotaOpen] = useState(false)
  const [pendingStart, setPendingStart] = useState<PendingNotebookStart | null>(null)
  const [name, setName] = useState(experiment.name)

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: getListExperimentsQueryKey() })
  const onMutationError = (error: unknown) => toast.error(toApiError(error).message)
  const quota = useNotebookQuota()

  const start = useStartNotebook({
    mutation: {
      onSuccess: () => {
        toast.success(`Notebook starting for “${experiment.name}”`)
        invalidate()
      },
      onError: (error) => {
        if (isNotebookQuotaError(error)) setQuotaOpen(true)
        else onMutationError(error)
      },
    },
  })
  const stop = useStopNotebook({
    mutation: {
      onSuccess: () => {
        toast.success(`Notebook stopping for "${experiment.name}"`)
        invalidate()
      },
      onError: onMutationError,
    },
  })
  const rename = useUpdateExperiment({
    mutation: {
      onSuccess: () => {
        toast.success("Experiment renamed")
        setRenameOpen(false)
        invalidate()
      },
      onError: onMutationError,
    },
  })
  const remove = useDeleteExperiment({
    mutation: {
      onSuccess: () => {
        toast.success(`Experiment “${experiment.name}” deleted`)
        invalidate()
      },
      onError: onMutationError,
    },
  })
  const archive = useArchiveExperiment({
    mutation: {
      onSuccess: () => {
        toast.success(`Archiving “${experiment.name}” (this can take a moment)`)
        invalidate()
      },
      onError: onMutationError,
    },
  })
  const restore = useRestoreExperiment({
    mutation: {
      onSuccess: () => {
        toast.success(`Restoring “${experiment.name}” (this can take a while)`)
        invalidate()
      },
      onError: onMutationError,
    },
  })

  const active = isNotebookActive(experiment.notebook?.status)
  const stopping = stop.isPending || experiment.notebook?.status === "TERMINATING"
  const notebookBusy = start.isPending || stop.isPending

  const label = liveLabel(experiment)

  const { shownStep, stepIndex } = stepParts(experiment)

  function toggleNotebook() {
    if (active) stop.mutate({ experimentId: experiment.id })
    else {
      const request: PendingNotebookStart = { experimentId: experiment.id, data: {} }
      setPendingStart(request)
      if (quota.full) setQuotaOpen(true)
      else start.mutate(request)
    }
  }

  function submitRename(event: React.FormEvent) {
    event.preventDefault()
    const next = name.trim()
    if (!next || next === experiment.name) return
    rename.mutate({ experimentId: experiment.id, data: { name: next } })
  }

  const deleteSize =
    experiment.size_bytes !== null && experiment.size_bytes !== undefined ? formatBytes(experiment.size_bytes) : null
  const deleteActiveJobs = activeJobCount(experiment)

  const archived = isArchived(experiment)
  const archiveInFlight = isArchiving(experiment)
  const readOnly = archived || archiveInFlight
  const failed = isArchivedFailed(experiment)
  const archiveStatus = useGetArchiveStatus(experiment.id, { query: { enabled: failed } })
  const reasonLabel = archiveStatus.data?.status === 200 ? archiveReasonLabel(archiveStatus.data.data.reason) : null
  const canArchive = !archived && !archiveInFlight && deleteActiveJobs === 0
  const canRestore = experiment.archive_state === "archived" || experiment.archive_state === "restore_failed"
  const stateLabel = archiveStateLabel(experiment)
  const busyLabel = label ?? (archiveInFlight ? stateLabel : null)

  return (
    // The whole card links to the wizard: the title anchor stretches an ::after
    // overlay across the card, and interactive elements rise above it with z-10.
    // DS cards are borderless (shadow-only), so hover means lift, not border.
    <Card className="relative pb-0 transition-shadow hover:shadow-md">
      <CardHeader>
        <div className="flex min-w-0 items-center gap-3">
          {/* Workflow icon, not progress; the step label and bar below carry progress. */}
          <ModuleIconTile category={experiment.module_category} />
          <div className="min-w-0">
            <CardTitle className="truncate leading-tight">
              {readOnly ? (
                // Archived experiments have no local files, so the wizard stays closed until restored.
                <span>{experiment.name}</span>
              ) : (
                <Link
                  to="/experiments/$experimentId"
                  params={{ experimentId: experiment.id }}
                  className="after:absolute after:inset-0"
                >
                  {experiment.name}
                </Link>
              )}
            </CardTitle>
            <p className="text-text-muted truncate text-sm" title={subtitle(experiment)}>
              {subtitle(experiment)}
            </p>
          </div>
        </div>
        <CardAction>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="relative z-10"
                aria-label={`Actions for ${experiment.name}`}
              >
                <Ellipsis size={18} />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => setRenameOpen(true)} disabled={readOnly}>
                <Pencil className="h-4 w-4" /> Rename
              </DropdownMenuItem>
              {/* TODO: duplicate endpoint is not available in the API yet */}
              <DropdownMenuItem disabled>
                <Copy className="h-4 w-4" /> Duplicate
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              {archived ? (
                <DropdownMenuItem onSelect={() => setRestoreOpen(true)} disabled={!canRestore || restore.isPending}>
                  <Undo2 className="h-4 w-4" /> Restore
                </DropdownMenuItem>
              ) : (
                <>
                  <DropdownMenuItem onSelect={toggleNotebook} disabled={notebookBusy || readOnly}>
                    {active ? (
                      <>
                        <Square fill="currentColor" className="h-4 w-4" /> Stop notebook
                      </>
                    ) : (
                      <>
                        <Play className="h-4 w-4" /> Start notebook
                      </>
                    )}
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onSelect={() => setArchiveOpen(true)}
                    disabled={!canArchive || archive.isPending}
                    title={deleteActiveJobs > 0 ? "Available when no jobs are running" : undefined}
                  >
                    <Archive className="h-4 w-4" /> Archive
                  </DropdownMenuItem>
                </>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="error" onSelect={() => setDeleteOpen(true)} disabled={readOnly}>
                <Trash2 className="h-4 w-4" /> Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </CardAction>
      </CardHeader>

      <CardContent className="space-y-2">
        {isArchivedFailed(experiment) && (
          <Alert variant="error">
            <AlertTitle>
              {experiment.archive_state === "archive_failed" ? "Archiving failed" : "Restoring failed"}
            </AlertTitle>
            <AlertDescription>
              {experiment.archive_state === "archive_failed"
                ? "Your files are unchanged on this drive; you can retry archiving."
                : "The archived copy is intact; you can retry restoring."}
              {reasonLabel ? ` (${reasonLabel})` : ""}
            </AlertDescription>
          </Alert>
        )}
        <div className="flex items-baseline justify-between gap-2 text-sm">
          <span>{`${STEP_LABELS[stepIndex]} · ${shownStep} of ${STEP_LABELS.length}`}</span>
          <span className={cn("flex items-center gap-1.5", busyLabel === null ? "text-text-muted" : undefined)}>
            {busyLabel !== null && <LoaderCircle size={14} className="animate-spin" aria-hidden="true" />}
            {label ?? stateLabel ?? `Active ${relativeTime(experiment.updated_at)}`}
          </span>
        </div>
        <div
          className="flex gap-1"
          role="progressbar"
          aria-valuenow={shownStep}
          aria-valuemin={0}
          aria-valuemax={5}
          aria-label={`Workflow progress: step ${shownStep} of 5`}
        >
          {STEP_LABELS.map((label, index) => (
            <span
              key={label}
              className={cn(
                "h-1.5 flex-1 rounded-full",
                // Completed steps fill solid, the current step stays tinted,
                // future steps stay grey; a published experiment fills all.
                experiment.status === "published" || index < stepIndex
                  ? "bg-primary"
                  : index === stepIndex
                    ? "bg-primary/40"
                    : "bg-surface-raised"
              )}
            />
          ))}
        </div>
        <StepDetails experiment={experiment} stepIndex={stepIndex} />
      </CardContent>

      {/* pt-3! must outrank the DS rule that pads [.border-t] footers to pt-6. The
          surface-raised + rounded-b footer band is the only legal surface step above
          the card's bg-surface. bg-background would match the page canvas and read
          as a hole in dark mode (and reverse the surface order in light). */}
      <CardFooter className="border-border bg-surface-raised gap-3 rounded-b-md border-t pt-3! pb-3 text-sm">
        <span className="text-text-muted truncate">{sourceLabel(experiment.source) ?? ""}</span>
        <span className="text-text-muted ml-auto flex shrink-0 items-center gap-3">
          {experiment.size_bytes !== null && experiment.size_bytes !== undefined && (
            <span className="flex items-center gap-1.5">
              <Database size={14} />
              {formatBytes(experiment.size_bytes)}
            </span>
          )}
          {!archived && (
            <span className="flex items-center gap-2">
              {stopping ? (
                <>
                  <LoaderCircle size={12} className="text-text-muted animate-spin" aria-hidden="true" />
                  <span>Stopping…</span>
                </>
              ) : (
                <>
                  <span
                    className={cn("h-2 w-2 rounded-full", active ? "bg-success" : "bg-text-muted/40")}
                    aria-hidden="true"
                  />
                  Notebook
                </>
              )}
            </span>
          )}
        </span>
      </CardFooter>

      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename experiment</DialogTitle>
          </DialogHeader>
          <form onSubmit={submitRename} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor={`rename-${experiment.id}`}>Name</Label>
              <Input
                id={`rename-${experiment.id}`}
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setRenameOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={rename.isPending || !name.trim()}>
                Save
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          {/* asChild keeps the list markup out of the <p> Radix renders by default. */}
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Trash2 className="text-error h-5 w-5" aria-hidden="true" />
              Delete experiment “{experiment.name}”?
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                <p>This permanently removes:</p>
                <List>
                  <li>
                    {archived ? "The archived copy in S3" : "All simulation files and results"}
                    {deleteSize ? ` (${deleteSize})` : ""}
                  </li>
                  {experiment.notebook && !archived && <li>The experiment’s notebook</li>}
                  {deleteActiveJobs > 0 && (
                    <li>
                      {deleteActiveJobs} running or queued {deleteActiveJobs === 1 ? "job" : "jobs"}
                    </li>
                  )}
                </List>
                <p className="text-error font-medium">This can’t be undone.</p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          {/* flex overrides the DS Alert's icon grid so the button shares the text row */}
          {!archived && (
            <InfoBanner className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 space-y-1">
                <AlertTitle>Want to keep the results?</AlertTitle>
                <AlertDescription>
                  Archiving frees {deleteSize ? `the same ${deleteSize}` : "disk space"} but keeps the data. You can
                  restore it later.
                </AlertDescription>
              </div>
              <Button
                variant="outline"
                className="self-end sm:shrink-0 sm:self-center"
                disabled={!canArchive}
                onClick={() => {
                  setDeleteOpen(false)
                  setArchiveOpen(true)
                }}
              >
                <Archive /> Archive instead
              </Button>
            </InfoBanner>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            {/* TODO: switch to variant="error" prop once CERIT-SC/design-system#108 (variant/size
                on AlertDialogAction) ships in a released @e-infra/design-system version */}
            <AlertDialogAction
              className={buttonVariants({ variant: "error" })}
              onClick={() => remove.mutate({ experimentId: experiment.id })}
              disabled={remove.isPending}
            >
              <Trash2 aria-hidden="true" />
              Delete experiment
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={archiveOpen} onOpenChange={setArchiveOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Archive className="h-5 w-5" aria-hidden="true" />
              Archive experiment “{experiment.name}”?
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                <p>
                  The data{deleteSize ? ` (${deleteSize})` : ""} moves to S3, and the local copy is deleted only after
                  the archive is verified.
                </p>
                <p>The experiment stays listed under Archived and can be restored anytime.</p>
                <p>The card is disabled until archiving finishes.</p>
                {active && <p>The running notebook will be stopped.</p>}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => archive.mutate({ experimentId: experiment.id })}
              disabled={archive.isPending}
            >
              <Archive aria-hidden="true" />
              Archive experiment
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={restoreOpen} onOpenChange={setRestoreOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Undo2 className="h-5 w-5" aria-hidden="true" />
              Restore experiment “{experiment.name}”?
            </AlertDialogTitle>
            <AlertDialogDescription>
              This downloads the archived copy{deleteSize ? ` (${deleteSize})` : ""} back to your drive and re-opens the
              experiment for editing.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => restore.mutate({ experimentId: experiment.id })}
              disabled={restore.isPending}
            >
              <Undo2 aria-hidden="true" />
              Restore experiment
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <NotebookQuotaDialog open={quotaOpen} onOpenChange={setQuotaOpen} pendingStart={pendingStart} />
    </Card>
  )
}
