import { lazy, memo, Suspense, useEffect, useMemo, useState } from "react"

import { Engine, JobStatus, type Simulation } from "@/api/generated/models"
import { ApiErrorAlert } from "@/shared/ui/api-error-alert"
import { HintTooltip } from "@/shared/ui/hint-tooltip"
import { LogPane } from "@/shared/ui/log-pane"
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
  Badge,
  Button,
  buttonVariants,
  cn,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
} from "@e-infra/design-system"
import {
  BarChart3,
  Info,
  LoaderCircle,
  Play,
  RotateCcw,
  Square,
  Terminal,
  TriangleAlert,
  X,
  type LucideIcon,
} from "lucide-react"

import { AVAILABLE_ANALYSES, PREPROCESSING_OPTIONS, type PreprocessingOption } from "./analysis-catalog"
import type { Analysis } from "./analysis-types"
import { analysisUnavailableReason } from "./analysis-unavailable"
import { getAnalysisLabel } from "./analysis-utils"
import {
  useAnalysisData,
  useAnalysisJobs,
  useAnalysisLogs,
  useAnalysisMutations,
  useAnalysisVariants,
  useAvailableAnalysisResults,
  useInvalidateAnalysisListsOnComplete,
} from "./use-analysis"

// Lazy — the ECharts bundle only loads once a result is actually rendered.
const AnalysisRenderer = lazy(() => import("./renderers").then((m) => ({ default: m.AnalysisRenderer })))
// Sim-status polls leave the chart props reference-stable; skip re-renders (setOption notMerge resets zoom).
const MemoAnalysisRenderer = memo(AnalysisRenderer)

const SELECT_NONE = "__none__"

type AnalysisPanelProps = {
  experimentId: string
  engine: Engine
  simulation: Simulation
  /** Test seam; production callers omit it. */
  pollMs?: number
}

/**
 * Analysis picker + runner: chooses an analysis, tracks its job, and renders
 * the produced graph. Empty, running, failed, and no-data states are durable
 * (never toast-only), matching the run step's model.
 */
export function AnalysisPanel({ experimentId, engine, simulation, pollMs }: AnalysisPanelProps) {
  const [confirmCancel, setConfirmCancel] = useState(false)
  const [showLogs, setShowLogs] = useState(false)
  const [selectedAnalysis, setSelectedAnalysis] = useState<string | null>(null)
  const [preprocessingMode, setPreprocessingMode] = useState(PREPROCESSING_OPTIONS[0].value)
  const [selectedVariant, setSelectedVariant] = useState<string | null>(null)

  // AMBER trajectories are handled as-is; the imaging options are GROMACS-only.
  const preprocessingOptions = useMemo<PreprocessingOption[]>(() => {
    if (engine === Engine.AMBER) {
      return PREPROCESSING_OPTIONS.filter((o) => o.value === PREPROCESSING_OPTIONS[0].value)
    }
    return PREPROCESSING_OPTIONS
  }, [engine])

  useEffect(() => {
    if (engine === Engine.AMBER && preprocessingMode !== PREPROCESSING_OPTIONS[0].value) {
      setPreprocessingMode(PREPROCESSING_OPTIONS[0].value)
    }
  }, [engine, preprocessingMode])

  const simulationPath = simulation.simulation_path

  // Steps stay mounted across simulation tab switches, so per-simulation picks
  // reset explicitly or B inherits A's analysis/variant. (PublishStep pattern.)
  useEffect(() => {
    setSelectedAnalysis(null)
    setSelectedVariant(null)
  }, [simulationPath])

  const jobsQuery = useAnalysisJobs(experimentId, simulationPath, pollMs)
  const jobs = jobsQuery.data?.status === 200 ? jobsQuery.data.data : undefined
  const activeJob = useMemo(
    () => jobs?.find((j) => j.status === JobStatus.RUNNING || j.status === JobStatus.PENDING),
    [jobs]
  )
  useInvalidateAnalysisListsOnComplete(experimentId, activeJob !== undefined)

  const resultsQuery = useAvailableAnalysisResults(experimentId, simulationPath)
  const availableResultsList = resultsQuery.data?.status === 200 ? resultsQuery.data.data : undefined
  const availableResults = useMemo(() => new Set(availableResultsList ?? []), [availableResultsList])

  const mutations = useAnalysisMutations(experimentId)

  // Resolve the picker value: explicit choice wins, then a running job's, then
  // the first analysis that already has results.
  const resolvedAnalysis = useMemo(() => {
    if (selectedAnalysis) return selectedAnalysis
    if (activeJob) return activeJob.analysis_name
    const analysisWithResults = AVAILABLE_ANALYSES.find(
      (a) => availableResults.has(a.resultName) || [...availableResults].some((r) => r.startsWith(`${a.resultName}-`))
    )
    return analysisWithResults?.value ?? null
  }, [selectedAnalysis, activeJob, availableResults])

  useEffect(() => {
    if (!selectedAnalysis && resolvedAnalysis) setSelectedAnalysis(resolvedAnalysis)
  }, [selectedAnalysis, resolvedAnalysis])

  const analysisConfig = useMemo(() => AVAILABLE_ANALYSES.find((a) => a.value === resolvedAnalysis), [resolvedAnalysis])
  const selectedResultName = analysisConfig?.resultName ?? null
  const submissionAnalysis = (selectedAnalysis ?? resolvedAnalysis) as
    (typeof AVAILABLE_ANALYSES)[number]["value"] | null

  const variantResults = useMemo(() => {
    if (!analysisConfig?.hasVariants || !selectedResultName) return []
    const pattern = new RegExp(`^${selectedResultName}-\\d+$`)
    return [...availableResults].filter((r) => pattern.test(r)).sort()
  }, [analysisConfig, selectedResultName, availableResults])

  // Auto-select the first variant once results arrive — the base file is the
  // variant index (not renderable), so never fetch it directly.
  useEffect(() => {
    if (analysisConfig?.hasVariants && !selectedVariant && variantResults.length > 0) {
      setSelectedVariant(variantResults[0])
    }
  }, [analysisConfig?.hasVariants, variantResults, selectedVariant])

  const hasResult = selectedResultName ? availableResults.has(selectedResultName) || variantResults.length > 0 : false

  const variantsQuery = useAnalysisVariants(
    experimentId,
    simulationPath,
    hasResult && analysisConfig?.hasVariants ? selectedResultName : null
  )
  const variantLabelMap = useMemo(() => {
    const map = new Map<string, string>()
    const variants = variantsQuery.data?.status === 200 ? variantsQuery.data.data : undefined
    for (const v of variants ?? []) map.set(v.analysis, v.name)
    return map
  }, [variantsQuery.data])

  const isRunningThis = activeJob?.analysis_name === resolvedAnalysis
  // For hasVariants analyses the base file is the variant index — never fetch or render it.
  const effectiveResultName = analysisConfig?.hasVariants ? selectedVariant : (selectedVariant ?? selectedResultName)

  const dataQuery = useAnalysisData(experimentId, simulationPath, hasResult ? effectiveResultName : null)
  const analysisData = dataQuery.data?.status === 200 ? dataQuery.data.data : undefined

  const unavailableReason = analysisUnavailableReason(simulation)
  const canSubmit = !unavailableReason && !!submissionAnalysis && !activeJob && !mutations.submit.isPending

  const lastJobForAnalysis = useMemo(() => {
    if (!jobs?.length || !selectedAnalysis) return null
    const filtered = jobs.filter((j) => j.analysis_name === selectedAnalysis)
    if (!filtered.length) return null
    return filtered.reduce((latest, job) => (new Date(job.created_at) > new Date(latest.created_at) ? job : latest))
  }, [jobs, selectedAnalysis])

  const completedWithNoResult = lastJobForAnalysis?.status === JobStatus.FINISHED && !hasResult
  const failedForAnalysis = !activeJob && lastJobForAnalysis?.status === JobStatus.ERROR

  // Partial-result marker: the server snapshots how far the simulation had
  // progressed when the analysis inputs were taken.
  const simProgress =
    lastJobForAnalysis?.status === JobStatus.FINISHED ? (lastJobForAnalysis.sim_progress ?? null) : null
  const calculatedPercent = simProgress !== null && simProgress < 1 ? Math.round(simProgress * 100) : null

  // Reset the logs pane whenever the active job changes or finishes.
  useEffect(() => {
    if (!activeJob || activeJob.status === JobStatus.PENDING) setShowLogs(false)
  }, [activeJob])
  const logJobId = showLogs ? (activeJob?.id ?? lastJobForAnalysis?.id ?? null) : null
  const logsQuery = useAnalysisLogs(
    experimentId,
    logJobId,
    activeJob !== undefined && activeJob.status !== JobStatus.PENDING,
    pollMs
  )
  const jobLogs = logsQuery.data?.status === 200 ? logsQuery.data.data : undefined

  const handleCalculate = () => {
    if (unavailableReason || !submissionAnalysis) return
    mutations.submit.mutate(simulationPath, submissionAnalysis, preprocessingMode)
  }

  if (jobs === undefined && jobsQuery.isPending) {
    return (
      <div className="space-y-4" aria-label="Loading analyses">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-72 w-full" />
      </div>
    )
  }
  if (jobsQuery.isError && jobs === undefined) {
    return <ApiErrorAlert error={jobsQuery.error} onRetry={() => void jobsQuery.refetch()} />
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-full sm:w-64">
          <Label htmlFor="analysis-select" className="mb-1.5 block text-sm font-medium">
            Analysis
          </Label>
          <Select
            value={resolvedAnalysis ?? SELECT_NONE}
            onValueChange={(value) => {
              if (value === SELECT_NONE) return
              setSelectedAnalysis(value)
              // Reset synchronously (same batched event): a stale variant from
              // the previous analysis must never become the fetched result.
              setSelectedVariant(null)
            }}
          >
            <SelectTrigger id="analysis-select" aria-label="Analysis" className="w-full">
              <SelectValue placeholder="Select analysis..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={SELECT_NONE} disabled>
                <em>Select analysis...</em>
              </SelectItem>
              {AVAILABLE_ANALYSES.map((a) => (
                <SelectItem key={a.value} value={a.value}>
                  <span className="flex items-center gap-2">
                    {a.label}
                    {(availableResults.has(a.resultName) ||
                      (a.hasVariants && [...availableResults].some((r) => r.startsWith(`${a.resultName}-`)))) && (
                      <Badge variant="secondary" className="px-1.5 py-0.5 text-[10px]">
                        ready
                      </Badge>
                    )}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="w-full sm:w-60">
          <div className="mb-1.5 flex items-center gap-1">
            <Label htmlFor="analysis-preprocessing-mode" className="block text-sm font-medium">
              Preprocessing
            </Label>
            <HintTooltip text="How the trajectory is treated before analysis: image re-centers molecules in the simulation box; image and fit also aligns them to the reference structure." />
          </div>
          <Select
            value={preprocessingMode}
            onValueChange={(value) => setPreprocessingMode(value as typeof preprocessingMode)}
          >
            <SelectTrigger id="analysis-preprocessing-mode" aria-label="Preprocessing" className="w-full">
              <SelectValue placeholder="Select preprocessing..." />
            </SelectTrigger>
            <SelectContent>
              {preprocessingOptions.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {resolvedAnalysis &&
          !activeJob &&
          (hasResult ? (
            <Button size="sm" variant="outline" onClick={handleCalculate} disabled={!canSubmit}>
              <RotateCcw aria-hidden />
              Re-calculate
            </Button>
          ) : (
            <Button size="sm" onClick={handleCalculate} disabled={!canSubmit}>
              <Play aria-hidden />
              Calculate
            </Button>
          ))}

        {!activeJob && calculatedPercent !== null && (
          <Badge variant="outline" className="border-warning text-warning ml-auto gap-1">
            <TriangleAlert className="h-3 w-3" aria-hidden />
            Calculated at {calculatedPercent}%
          </Badge>
        )}

        {activeJob && (
          <>
            {/* Status unit the same height as the sm buttons keeps the row on
                one baseline; the analysis name is bold (design mock). */}
            <span
              role="status"
              className="border-border bg-surface inline-flex h-8 items-center gap-2 rounded-md border px-3 text-sm"
            >
              <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />
              Calculating{" "}
              <strong className="font-semibold">
                {AVAILABLE_ANALYSES.find((a) => a.value === activeJob.analysis_name)?.label ?? activeJob.analysis_name}
              </strong>
            </span>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="border-error text-error hover:bg-error/10 hover:text-error"
              onClick={() => setConfirmCancel(true)}
            >
              <Square fill="currentColor" aria-hidden />
              Stop calculation
            </Button>
            {activeJob.status !== JobStatus.PENDING && (
              <Button size="sm" variant="ghost" onClick={() => setShowLogs((value) => !value)}>
                <Terminal aria-hidden />
                {showLogs ? "Hide logs" : "View logs"}
              </Button>
            )}
          </>
        )}
      </div>

      {/* A failed run gets one clear, durable banner in the results column
          (it can also overlay still-valid older results) — no floating chip
          in the run row. */}
      {failedForAnalysis && (
        <Alert role="alert" variant="error">
          <AlertTitle>Previous analysis run failed.</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
            <span>Inspect the logs to understand the failure before retrying.</span>
            <Button size="sm" variant="ghost" onClick={() => setShowLogs((value) => !value)}>
              <Terminal aria-hidden />
              {showLogs ? "Hide logs" : "View logs"}
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {unavailableReason && !hasResult && <p className="text-text-muted text-xs">{unavailableReason}</p>}

      {showLogs && <LogPane logs={jobLogs ?? ""} isLoading={logsQuery.isLoading} />}

      <div>
        {/* View concern, not a run concern: picks which computed variant the
            chart below shows, so it lives with the results, not the run row. */}
        {resolvedAnalysis && hasResult && variantResults.length > 0 && (
          <div className="mb-3 flex items-center justify-end gap-2">
            <span className="text-text-muted text-sm">Variant</span>
            <Select value={selectedVariant ?? undefined} onValueChange={setSelectedVariant}>
              <SelectTrigger className="w-64" aria-label="Variant">
                <SelectValue placeholder="Select variant..." />
              </SelectTrigger>
              <SelectContent>
                {variantResults.map((v) => (
                  <SelectItem key={v} value={v}>
                    {variantLabelMap.get(v) ?? getAnalysisLabel(v)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {!resolvedAnalysis && <Placeholder icon={BarChart3} message="Select an analysis to view or calculate." />}

        {resolvedAnalysis && isRunningThis && !hasResult && (
          <Placeholder icon={LoaderCircle} spinning message="Results are being calculated…" />
        )}

        {resolvedAnalysis &&
          !isRunningThis &&
          !hasResult &&
          !failedForAnalysis &&
          (completedWithNoResult ? (
            <Placeholder
              icon={Info}
              message="Analysis produced no data."
              hint="This analysis may not apply to your system (e.g., no lipid membrane detected)."
            />
          ) : (
            <Placeholder
              icon={BarChart3}
              message="No results yet."
              hint="Choose an analysis and click Calculate to run it."
            />
          ))}

        {resolvedAnalysis && hasResult && dataQuery.isLoading && (
          <Placeholder icon={LoaderCircle} spinning message="Loading analysis data…" />
        )}

        {resolvedAnalysis && hasResult && dataQuery.isError && (
          <ApiErrorAlert error={dataQuery.error} onRetry={() => void dataQuery.refetch()} />
        )}

        {resolvedAnalysis &&
          hasResult &&
          !dataQuery.isLoading &&
          !dataQuery.isError &&
          analysisData !== undefined &&
          effectiveResultName && (
            <Suspense fallback={<Skeleton className="h-72 w-full" />}>
              <MemoAnalysisRenderer analysisName={effectiveResultName} data={analysisData as Analysis} />
            </Suspense>
          )}
      </div>

      {/* AlertDialogAction has no variant prop in DS ≤ 0.1.9 — buttonVariants workaround
          (https://github.com/CERIT-SC/design-system/pull/108). */}
      <AlertDialog open={confirmCancel} onOpenChange={setConfirmCancel}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <X className="text-error" aria-hidden />
              Cancel analysis job
            </AlertDialogTitle>
            <AlertDialogDescription>
              Stop the current analysis job? This run will be terminated and any partial output may be incomplete.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep running</AlertDialogCancel>
            <AlertDialogAction
              className={buttonVariants({ variant: "error" })}
              onClick={() => {
                if (activeJob) mutations.remove.mutate(activeJob.id)
                setConfirmCancel(false)
              }}
              disabled={mutations.remove.isPending}
            >
              Cancel job
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function Placeholder({
  icon: Icon,
  spinning = false,
  message,
  hint,
}: {
  icon: LucideIcon
  spinning?: boolean
  message: string
  hint?: string
}) {
  return (
    <div className="border-border bg-surface flex h-full flex-1 items-center justify-center rounded-lg border-2 border-dashed py-16">
      <div className="space-y-2 text-center">
        <Icon className={cn("text-text-muted/70 mx-auto h-12 w-12", spinning && "animate-spin")} />
        <p className="text-text-muted text-sm">{message}</p>
        {hint && <p className="text-text-muted/80 text-xs">{hint}</p>}
      </div>
    </div>
  )
}
