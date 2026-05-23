import { useEffect, useMemo, useRef, useState } from "react"

import { useQueryClient } from "@tanstack/react-query"
import { BarChart3, CircleAlert, Info, Loader2, Play, RefreshCw, Terminal, X } from "lucide-react"

import { statusBadgeClass } from "@/lib/status"
import { cn } from "@/lib/utils"
import {
  AnalysisPreprocessingMode,
  AVAILABLE_ANALYSES,
  type Analysis,
  type AnalysisPreprocessingMode as AnalysisPreprocessingModeValue,
  type AnalysisType,
} from "@/util/analysis-types"
import { getAnalysisLabel } from "@/util/analysis-utils"
import { Engine } from "@/util/const"
import type { FileOption } from "@/util/types"
import { getJobStatusVariant } from "@/util/types"
import {
  useAnalysisData,
  useAnalysisJobs,
  useAnalysisLogs,
  useAnalysisVariants,
  useAvailableAnalysisResults,
  useDeleteAnalysis,
  useSubmitAnalysis,
} from "@/hooks/use-analysis"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import AnalysisRenderer from "@/components/analysis/renderers"
import ConfirmDialog from "@/components/ConfirmDialog"
import LogsView from "@/components/LogsView"

interface AnalysisPanelProps {
  experimentId: string
  engine: Engine
  structureFile: FileOption | null
  coordsFile: FileOption | null
  topologyFile: FileOption | null
  topologyRequired: boolean
  preprocessingMode: AnalysisPreprocessingModeValue
  setPreprocessingMode: (mode: AnalysisPreprocessingModeValue) => void
  selectedAnalysis: AnalysisType | null
  setSelectedAnalysis: (analysis: AnalysisType | null) => void
}

const PREPROCESSING_OPTIONS: Array<{ value: AnalysisPreprocessingModeValue; label: string }> = [
  { value: AnalysisPreprocessingMode.AS_IS, label: "Use Files As-Is" },
  { value: AnalysisPreprocessingMode.IMAGE, label: "Image Only" },
  { value: AnalysisPreprocessingMode.IMAGE_FIT, label: "Image and Fit" },
]

const AnalysisPanel = ({
  experimentId,
  engine,
  structureFile,
  coordsFile,
  topologyFile,
  topologyRequired,
  preprocessingMode,
  setPreprocessingMode,
  selectedAnalysis,
  setSelectedAnalysis,
}: AnalysisPanelProps) => {
  const preprocessingOptions = useMemo(() => {
    if (engine === Engine.AMBER) {
      return PREPROCESSING_OPTIONS.filter((o) => o.value === AnalysisPreprocessingMode.AS_IS)
    }
    return PREPROCESSING_OPTIONS
  }, [engine])

  useEffect(() => {
    if (engine === Engine.AMBER && preprocessingMode !== AnalysisPreprocessingMode.AS_IS) {
      setPreprocessingMode(AnalysisPreprocessingMode.AS_IS)
    }
  }, [engine, preprocessingMode, setPreprocessingMode])

  const queryClient = useQueryClient()
  const [confirmCancelDialog, setConfirmCancelDialog] = useState(false)

  const { data: jobs } = useAnalysisJobs(experimentId)
  const activeJob = useMemo(() => jobs?.find((j) => j.status === "RUNNING" || j.status === "PENDING"), [jobs])

  const { data: availableResultsList } = useAvailableAnalysisResults(experimentId)

  // Invalidate the results list and cached chart data when a job finishes.
  const hadActiveJobRef = useRef(false)
  useEffect(() => {
    const isActive = !!activeJob
    if (hadActiveJobRef.current && !isActive) {
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "analysis-results"] })
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "analysis-variants"] })
    }
    hadActiveJobRef.current = isActive
  }, [activeJob, queryClient, experimentId])
  const submitAnalysis = useSubmitAnalysis(experimentId)
  const deleteAnalysis = useDeleteAnalysis(experimentId)
  const [selectedVariant, setSelectedVariant] = useState<string | null>(null)

  useEffect(() => {
    setSelectedVariant(null)
  }, [selectedAnalysis])

  const availableResults = useMemo(() => new Set(availableResultsList ?? []), [availableResultsList])

  const resolvedAnalysis = useMemo(() => {
    if (selectedAnalysis) return selectedAnalysis
    if (activeJob) return activeJob.analysis_name

    const analysisWithResults = AVAILABLE_ANALYSES.find(
      (a) => availableResults.has(a.resultName) || [...availableResults].some((r) => r.startsWith(a.resultName + "-"))
    )
    return analysisWithResults?.value ?? null
  }, [selectedAnalysis, activeJob, availableResults])

  useEffect(() => {
    if (!selectedAnalysis && resolvedAnalysis) setSelectedAnalysis(resolvedAnalysis)
  }, [selectedAnalysis, resolvedAnalysis, setSelectedAnalysis])

  const analysisConfig = useMemo(() => AVAILABLE_ANALYSES.find((a) => a.value === resolvedAnalysis), [resolvedAnalysis])
  const selectedResultName = analysisConfig?.resultName ?? null
  const submissionAnalysis = selectedAnalysis ?? resolvedAnalysis
  const submitRequiresTopology = topologyRequired || !!analysisConfig?.requiresTopology

  const variantResults = useMemo(() => {
    if (!analysisConfig?.hasVariants || !selectedResultName) return []
    const pattern = new RegExp(`^${selectedResultName}-\\d+$`)
    return [...availableResults].filter((r) => pattern.test(r)).sort()
  }, [analysisConfig, selectedResultName, availableResults])

  // Auto-select first variant for hasVariants analyses once results arrive.
  // The base result file is the variant index (not renderable), so never fetch it directly.
  useEffect(() => {
    if (analysisConfig?.hasVariants && !selectedVariant && variantResults.length > 0) {
      setSelectedVariant(variantResults[0])
    }
  }, [analysisConfig?.hasVariants, variantResults, selectedVariant])

  const hasResult = selectedResultName ? availableResults.has(selectedResultName) || variantResults.length > 0 : false

  const { data: analysisVariants } = useAnalysisVariants(
    experimentId,
    hasResult && analysisConfig?.hasVariants ? selectedResultName : null
  )
  const variantLabelMap = useMemo(() => {
    const map = new Map<string, string>()
    for (const v of analysisVariants ?? []) map.set(v.analysis, v.name)
    return map
  }, [analysisVariants])
  const isRunningThis = activeJob?.analysis_name === resolvedAnalysis

  // For hasVariants analyses the base file is the variant index — never fetch or render it.
  const effectiveResultName = analysisConfig?.hasVariants ? selectedVariant : (selectedVariant ?? selectedResultName)

  const { data: analysisData, isLoading: isLoadingData } = useAnalysisData(
    experimentId,
    hasResult ? effectiveResultName : null
  )

  const canSubmit =
    (!!structureFile || !!topologyFile) &&
    !!coordsFile &&
    !!submissionAnalysis &&
    (!submitRequiresTopology || !!topologyFile) &&
    !activeJob &&
    !submitAnalysis.isPending

  const submitCurrentAnalysis = () => {
    if (
      (!structureFile && !topologyFile) ||
      !coordsFile ||
      !submissionAnalysis ||
      (submitRequiresTopology && !topologyFile)
    )
      return

    submitAnalysis.mutate({
      analysis: submissionAnalysis,
      trajectory_file: coordsFile.path,
      preprocessing_mode: preprocessingMode,
      ...(structureFile && { structure_file: structureFile.path }),
      ...(topologyFile && { topology_file: topologyFile.path }),
    })
  }

  const handleCalculate = () => {
    submitCurrentAnalysis()
  }

  const lastJob = useMemo(() => {
    if (!jobs?.length) return null
    return jobs.reduce((latest, job) => (new Date(job.created_at) > new Date(latest.created_at) ? job : latest))
  }, [jobs])

  const lastJobForAnalysis = useMemo(() => {
    if (!jobs?.length || !selectedAnalysis) return null
    const filtered = jobs.filter((j) => j.analysis_name === selectedAnalysis)
    if (!filtered.length) return null
    return filtered.reduce((latest, job) => (new Date(job.created_at) > new Date(latest.created_at) ? job : latest))
  }, [jobs, selectedAnalysis])

  const completedWithNoResult = lastJobForAnalysis?.status === "TERMINATED" && !hasResult
  const failedJobForAnalysis = !activeJob && lastJobForAnalysis?.status === "ERROR"

  const [showLogs, setShowLogs] = useState(false)
  useEffect(() => {
    if (!activeJob || activeJob.status === "PENDING") setShowLogs(false)
  }, [activeJob])
  const logJobId = showLogs ? (activeJob?.id ?? lastJob?.id ?? null) : null
  const { data: jobLogs, isLoading: jobLogsLoading } = useAnalysisLogs(experimentId, logJobId, !!activeJob)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-56 flex-1 sm:max-w-sm">
          <Label htmlFor="analysis-select" className="mb-1.5 block text-sm font-medium">
            Analysis
          </Label>
          <Select
            value={resolvedAnalysis ?? undefined}
            onValueChange={(value) => setSelectedAnalysis(value as AnalysisType)}
          >
            <SelectTrigger id="analysis-select" className="w-full">
              <SelectValue placeholder="Select analysis..." />
            </SelectTrigger>
            <SelectContent>
              {AVAILABLE_ANALYSES.map((a) => (
                <SelectItem key={a.value} value={a.value}>
                  <span className="flex items-center gap-2">
                    {a.label}
                    {(availableResults.has(a.resultName) ||
                      (a.hasVariants && [...availableResults].some((r) => r.startsWith(a.resultName + "-")))) && (
                      <span className="bg-primary/15 text-primary rounded px-1.5 py-0.5 text-[10px] font-medium">
                        ready
                      </span>
                    )}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="w-full sm:w-60">
          <Label htmlFor="analysis-preprocessing-mode" className="mb-1.5 block text-sm font-medium">
            Preprocessing
          </Label>
          <Select
            value={preprocessingMode}
            onValueChange={(value) => setPreprocessingMode(value as AnalysisPreprocessingModeValue)}
          >
            <SelectTrigger id="analysis-preprocessing-mode" className="w-full">
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

        {resolvedAnalysis && (
          <>
            {isRunningThis ? (
              <Button size="sm" disabled>
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                Running...
              </Button>
            ) : hasResult ? (
              <Button size="sm" variant="outline" onClick={handleCalculate} disabled={!canSubmit}>
                <RefreshCw className="mr-1 h-3.5 w-3.5" />
                Re-calculate
              </Button>
            ) : (
              <Button size="sm" onClick={handleCalculate} disabled={!canSubmit}>
                <Play className="mr-1 h-3.5 w-3.5" />
                Calculate
              </Button>
            )}
          </>
        )}

        {hasResult && variantResults.length > 0 && (
          <Select value={selectedVariant ?? undefined} onValueChange={setSelectedVariant}>
            <SelectTrigger className="w-44">
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
        )}

        {activeJob && (
          <>
            <span
              className={cn(
                "ml-auto inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
                statusBadgeClass(getJobStatusVariant(activeJob.status))
              )}
            >
              <Loader2 className="h-3 w-3 animate-spin" />
              {activeJob.status}
              {activeJob.analysis_name !== resolvedAnalysis && (
                <span className="opacity-75">
                  (
                  {AVAILABLE_ANALYSES.find((a) => a.value === activeJob.analysis_name)?.label ??
                    activeJob.analysis_name}
                  )
                </span>
              )}
              <button
                type="button"
                aria-label="Cancel running analysis"
                className="hover:bg-background/20 focus-visible:ring-ring rounded-full p-0.5 transition-colors focus-visible:ring-2 focus-visible:outline-hidden"
                onClick={() => setConfirmCancelDialog(true)}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
            {activeJob.status !== "PENDING" && (
              <Button
                size="sm"
                variant="ghost"
                className="h-6 px-2 text-xs"
                onClick={() => setShowLogs((value) => !value)}
              >
                <Terminal className="mr-1 h-3 w-3" />
                {showLogs ? "Hide logs" : "View logs"}
              </Button>
            )}
          </>
        )}

        {!activeJob && lastJob?.status === "ERROR" && (
          <>
            <span
              className={cn(
                "ml-auto inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
                statusBadgeClass("destructive")
              )}
            >
              <CircleAlert className="h-3 w-3" />
              Failed
            </span>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 px-2 text-xs"
              onClick={() => setShowLogs((value) => !value)}
            >
              <Terminal className="mr-1 h-3 w-3" />
              {showLogs ? "Hide logs" : "View logs"}
            </Button>
          </>
        )}
      </div>

      {resolvedAnalysis &&
        !hasResult &&
        ((!structureFile && !topologyFile) || !coordsFile || (submitRequiresTopology && !topologyFile)) && (
          <p className="text-muted-foreground text-xs">
            {submitRequiresTopology
              ? preprocessingMode === AnalysisPreprocessingMode.AS_IS
                ? "Select structure, trajectory, and topology files in the sidebar to run this analysis."
                : "Select structure, trajectory, and simulation TPR files in the sidebar to run analyses with preprocessing."
              : !structureFile && !topologyFile
                ? "Select a structure file or a topology file and a trajectory file in the sidebar to run this analysis."
                : !coordsFile
                  ? "Select trajectory file in the sidebar to run this analysis."
                  : "Select structure and trajectory files in the sidebar to run this analysis."}
          </p>
        )}

      {showLogs && <LogsView logs={jobLogs ?? ""} isLoading={jobLogsLoading} />}

      <div>
        {!resolvedAnalysis && (
          <div className="border-muted-foreground/25 bg-muted flex h-full flex-1 items-center justify-center rounded-lg border-2 border-dashed">
            <div className="space-y-2 text-center">
              <BarChart3 className="text-muted-foreground/50 mx-auto h-12 w-12" />
              <p className="text-muted-foreground text-sm">Select an analysis to view or calculate.</p>
            </div>
          </div>
        )}

        {resolvedAnalysis && isRunningThis && (
          <div className="border-muted-foreground/25 bg-muted flex h-full flex-1 items-center justify-center rounded-lg border-2 border-dashed">
            <div className="space-y-2 text-center">
              <Loader2 className="text-muted-foreground/50 mx-auto h-12 w-12 animate-spin" />
              <p className="text-muted-foreground text-sm">Analysis is running...</p>
            </div>
          </div>
        )}

        {resolvedAnalysis && !isRunningThis && !hasResult && (
          <div className="border-muted-foreground/25 bg-muted flex h-full flex-1 items-center justify-center rounded-lg border-2 border-dashed py-5">
            {failedJobForAnalysis ? (
              <div className="space-y-2 px-6 text-center">
                <CircleAlert className="text-destructive/70 mx-auto h-12 w-12" />
                <p className="text-sm font-medium">Previous analysis run failed.</p>
                <p className="text-muted-foreground text-xs">
                  Inspect the logs to understand the failure before retrying.
                </p>
              </div>
            ) : completedWithNoResult ? (
              <div className="space-y-2 text-center">
                <Info className="text-muted-foreground/50 mx-auto h-12 w-12" />
                <p className="text-muted-foreground text-sm">Analysis produced no data.</p>
                <p className="text-muted-foreground/75 text-xs">
                  This analysis may not apply to your system (e.g., no lipid membrane detected).
                </p>
              </div>
            ) : (
              <div className="space-y-2 text-center">
                <BarChart3 className="text-muted-foreground/50 mx-auto h-12 w-12" />
                <p className="text-muted-foreground text-sm">No results yet.</p>
                <p className="text-muted-foreground/75 text-xs">
                  {submitRequiresTopology
                    ? preprocessingMode === AnalysisPreprocessingMode.AS_IS
                      ? 'Select the required files and click "Calculate" to run this analysis.'
                      : 'Select the simulation TPR and click "Calculate" to run this analysis.'
                    : 'Select the required files and click "Calculate" to run this analysis.'}
                </p>
              </div>
            )}
          </div>
        )}

        {resolvedAnalysis && hasResult && isLoadingData && (
          <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            Loading analysis data...
          </div>
        )}

        {resolvedAnalysis && hasResult && !isLoadingData && !!analysisData && effectiveResultName && (
          <AnalysisRenderer analysisName={effectiveResultName} data={analysisData as Analysis} />
        )}
      </div>

      <ConfirmDialog
        open={confirmCancelDialog}
        setOpen={setConfirmCancelDialog}
        title="Cancel analysis job"
        message="Stop the current analysis job? This run will be terminated and any partial output may be incomplete."
        confirmText="Cancel job"
        confirmColor="destructive"
        onConfirm={async () => {
          if (!activeJob) return
          await deleteAnalysis.mutateAsync(activeJob.id)
        }}
      />
    </div>
  )
}

export default AnalysisPanel
