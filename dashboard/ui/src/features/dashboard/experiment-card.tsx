import { useState } from "react"

import { toApiError } from "@/api/errors"
import {
  getListExperimentsQueryKey,
  useDeleteExperiment,
  useListAnalysisJobs,
  useListAnalysisResults,
  useListAnalysisTypes,
  useStartNotebook,
  useStopNotebook,
  useUpdateExperiment,
} from "@/api/generated/client"
import type { Experiment } from "@/api/generated/models"
import {
  isNotebookQuotaError,
  NotebookQuotaDialog,
  useNotebookQuota,
  type PendingNotebookStart,
} from "@/features/notebook"
import { ENGINE_LABELS } from "@/shared/engine"
import { formatBytes, formatTime, relativeTime } from "@/shared/format"
import { isNotebookActive } from "@/shared/pod-status"
import { sourceLabel } from "@/shared/source"
import { InfoBanner } from "@/shared/ui/info-banner"
import {
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
import {
  Activity,
  Archive,
  Award,
  Copy,
  Database,
  Ellipsis,
  FlaskConical,
  LoaderCircle,
  Pencil,
  Play,
  Rocket,
  SlidersHorizontal,
  Square,
  Trash2,
  Upload,
  type LucideIcon,
} from "lucide-react"
import { toast } from "sonner"

const STEP_LABELS = ["Setup", "Tune", "Run", "Analyze", "Publish"] as const

const IDLE_STATUSES = new Set(["setup", "setup complete", "published"])

// Phases with work in flight get the spinner (matches the mock's live statuses).
const SPINNING_STATUSES = new Set(["simulating", "tuning", "analyzing"])

// The API step IS the phase index (Setup 0 .. Analyze 3, publish states 4) —
// consumed directly; the shown counter counts from 1.
function stepParts(experiment: Experiment): { shownStep: number; stepIndex: number } {
  const step = Math.max(0, Math.min(experiment.step ?? 0, STEP_LABELS.length - 1))
  return { shownStep: step + 1, stepIndex: step }
}

// Icon/color keyed by the workflow step (mock: flask=setup, sliders=tune,
// rocket=run, pulse=analyze, award=publish); module/engine stay text in the subtitle.
const STEP_ICONS: { Icon: LucideIcon; className: string }[] = [
  { Icon: FlaskConical, className: "bg-surface-raised text-text-muted" },
  { Icon: SlidersHorizontal, className: "bg-info text-info-foreground" },
  { Icon: Rocket, className: "bg-success text-success-foreground" },
  { Icon: Activity, className: "bg-warning text-warning-foreground" },
  { Icon: Award, className: "bg-primary text-primary-foreground" },
]

function subtitle(experiment: Experiment): string {
  return `${experiment.module_name ?? "Custom"} · ${ENGINE_LABELS[experiment.engine]}`
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function statusLine(experiment: Experiment): string {
  const status = experiment.status?.trim()
  if (!status || IDLE_STATUSES.has(status)) return `Active ${relativeTime(experiment.updated_at)}`
  if (status === "simulating") {
    const job = experiment.simulation_jobs.find((candidate) => candidate.status === "RUNNING")
    const done = typeof job?.nsteps_done === "number" ? job.nsteps_done : undefined
    if (job?.nsteps && done) return `${capitalize(status)} · ${Math.round((done / job.nsteps) * 100)}%`
  }
  return capitalize(status)
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

const latest = <T extends { created_at: string }>(jobs: T[]) =>
  jobs.reduce<T | undefined>((best, job) => (!best || job.created_at > best.created_at ? job : best), undefined)

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
  const params = { simulation_path: simulationPath }
  const queries = { query: { enabled: simulationPath !== "", retry: false } }
  const jobs = useListAnalysisJobs(experiment.id, params, queries)
  const models = useListAnalysisResults(experiment.id, params, queries)
  // The pool is the hard MDDB workflow set, not the jobs submitted so far — it is
  // experiment-independent, so it needs no simulation_path gate and never goes stale.
  const types = useListAnalysisTypes(experiment.id, { query: { retry: false, staleTime: Number.POSITIVE_INFINITY } })

  if (!simulationPath) {
    return (
      <>
        <DetailRow label="Models" value="N/A" />
        <DetailRow label="Analyses" value="N/A" />
      </>
    )
  }

  const ready = (jobs.data?.status === 200 ? jobs.data.data : undefined)?.filter(
    (job) => job.status === "FINISHED"
  ).length
  const total = types.data?.status === 200 ? types.data.data.length : undefined
  return (
    <>
      <DetailRow label="Models" value={models.data?.status === 200 ? String(models.data.data.length) : "…"} />
      <DetailRow
        label="Analyses"
        value={ready === undefined || total === undefined ? "…" : `${ready} of ${total} ready`}
      />
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

const DELETE_ACTIVE_STATUSES = new Set(["PENDING", "RUNNING"])

/** Jobs that would be interrupted by a delete (PENDING covers queued; the API has no QUEUED status). */
function activeJobCount(experiment: Experiment): number {
  return (
    experiment.simulation_jobs.filter((job) => DELETE_ACTIVE_STATUSES.has(job.status)).length +
    experiment.tuner_jobs.filter((job) => DELETE_ACTIVE_STATUSES.has(job.tuner_status)).length +
    experiment.analysis_jobs.filter((job) => DELETE_ACTIVE_STATUSES.has(job.status)).length
  )
}

export function ExperimentCard({ experiment }: ExperimentCardProps) {
  const queryClient = useQueryClient()
  const [renameOpen, setRenameOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
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
        toast.success(`Notebook stopping for “${experiment.name}”`)
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

  const active = isNotebookActive(experiment.notebook?.status)
  const notebookBusy = start.isPending || stop.isPending

  const { shownStep, stepIndex } = stepParts(experiment)
  // The publish step has a distinct icon per state (upload while publishing, award once published).
  const { Icon: StepIcon, className: stepIconClass } =
    stepIndex === 4
      ? experiment.status === "published"
        ? { Icon: Award, className: "bg-primary text-primary-foreground" }
        : { Icon: Upload, className: "bg-info text-info-foreground" }
      : STEP_ICONS[stepIndex]

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

  return (
    // The whole card links to the wizard: the title anchor stretches an ::after
    // overlay across the card, and interactive elements rise above it with z-10.
    // DS cards are borderless (shadow-only), so hover means lift, not border.
    <Card className="relative pb-0 transition-shadow hover:shadow-md">
      <CardHeader>
        <div className="flex min-w-0 items-center gap-3">
          <span
            className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-lg", stepIconClass)}
            aria-hidden="true"
          >
            <StepIcon size={20} />
          </span>
          <div className="min-w-0">
            <CardTitle className="truncate leading-tight">
              <Link
                to="/experiments/$experimentId"
                params={{ experimentId: experiment.id }}
                className="after:absolute after:inset-0"
              >
                {experiment.name}
              </Link>
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
              <DropdownMenuItem onSelect={() => setRenameOpen(true)}>
                <Pencil className="h-4 w-4" /> Rename
              </DropdownMenuItem>
              {/* TODO: duplicate endpoint is not available in the API yet */}
              <DropdownMenuItem disabled>
                <Copy className="h-4 w-4" /> Duplicate
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={toggleNotebook} disabled={notebookBusy}>
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
              {/* TODO: archive support is not implemented in the API yet */}
              <DropdownMenuItem disabled>
                <Archive className="h-4 w-4" /> Archive
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="error" onSelect={() => setDeleteOpen(true)}>
                <Trash2 className="h-4 w-4" /> Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </CardAction>
      </CardHeader>

      <CardContent className="space-y-2">
        <div className="flex items-baseline justify-between gap-2 text-sm">
          <span>{`${STEP_LABELS[stepIndex]} · ${shownStep} of ${STEP_LABELS.length}`}</span>
          <span
            className={cn(
              "flex items-center gap-1.5",
              SPINNING_STATUSES.has(experiment.status ?? "") ? undefined : "text-text-muted"
            )}
          >
            {SPINNING_STATUSES.has(experiment.status ?? "") && (
              <LoaderCircle size={14} className="animate-spin" aria-hidden="true" />
            )}
            {statusLine(experiment)}
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
          the card's bg-surface — bg-background would match the page canvas and read
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
          <span className="flex items-center gap-2">
            <span
              className={cn("h-2 w-2 rounded-full", active ? "bg-success" : "bg-text-muted/40")}
              aria-hidden="true"
            />
            Notebook
          </span>
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
                  <li>All simulation files and results{deleteSize ? ` (${deleteSize})` : ""}</li>
                  {experiment.notebook && <li>The experiment’s notebook</li>}
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
          <InfoBanner className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 space-y-1">
              <AlertTitle>Want to keep the results?</AlertTitle>
              <AlertDescription>
                Archiving frees {deleteSize ? `the same ${deleteSize}` : "disk space"} but keeps the data. You can
                restore it later.
              </AlertDescription>
            </div>
            {/* TODO: archive support is not implemented in the API yet — enable when it lands */}
            <Button variant="outline" className="self-end sm:shrink-0 sm:self-center" disabled>
              <Archive /> Archive instead
            </Button>
          </InfoBanner>
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

      <NotebookQuotaDialog open={quotaOpen} onOpenChange={setQuotaOpen} pendingStart={pendingStart} />
    </Card>
  )
}
