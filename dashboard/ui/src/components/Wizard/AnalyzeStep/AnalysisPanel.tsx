import { useEffect, useMemo, useState } from "react"

import { Activity, BarChart3, CircleAlert, Loader2, Play, RefreshCw, Shapes, Terminal } from "lucide-react"

import { AVAILABLE_ANALYSES, type Analysis, type AnalysisType } from "@/util/analysis-types"
import type { FileOption, JobStatus } from "@/util/types"
import { getJobStatusVariant } from "@/util/types"
import { useAnalysisData, useAnalysisJobs, useAnalysisLogs, useAnalysisResults, useAnalysisVariants, useSubmitAnalysis } from "@/hooks/use-analysis"
import { getAnalysisLabel } from "@/util/analysis-utils"
import { statusBadgeClass } from "@/lib/status"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import FileSelector from "@/components/FileSelector"
import AnalysisRenderer from "@/components/analysis/renderers"

interface AnalysisPanelProps {
  experimentId: string
}

const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  PENDING: "Pending",
  RUNNING: "Running",
  TERMINATED: "Completed",
  ERROR: "Failed",
  UNKNOWN: "Unknown",
}

const STRUCTURE_FORMATS = ["pdb", "gro"]
const COORDINATE_FORMATS = ["xtc", "trr"]

const AnalysisPanel = ({ experimentId }: AnalysisPanelProps) => {
  const [structureFile, setStructureFile] = useState<FileOption | null>(null)
  const [coordsFile, setCoordsFile] = useState<FileOption | null>(null)

  useEffect(() => {
    if (!structureFile) setCoordsFile(null)
  }, [structureFile])

  const { data: jobs } = useAnalysisJobs(experimentId)
  const activeJob = useMemo(() => jobs?.find((j) => j.status === "RUNNING" || j.status === "PENDING"), [jobs])
  const { data: results } = useAnalysisResults(experimentId, !!activeJob)
  const submitAnalysis = useSubmitAnalysis(experimentId)
  const [selectedAnalysis, setSelectedAnalysis] = useState<AnalysisType | null>(null)
  const [selectedVariant, setSelectedVariant] = useState<string | null>(null)

  // Reset variant whenever the analysis changes
  useEffect(() => setSelectedVariant(null), [selectedAnalysis])

  const availableResults = useMemo(() => new Set(results?.map((r) => r.name) ?? []), [results])

  const analysisConfig = useMemo(() => AVAILABLE_ANALYSES.find((a) => a.value === selectedAnalysis), [selectedAnalysis])
  const selectedResultName = analysisConfig?.resultName ?? null

  // For analyses that produce per-interaction numbered variants (base-00, base-01, …)
  const variantResults = useMemo(() => {
    if (!analysisConfig?.hasVariants || !selectedResultName) return []
    const pattern = new RegExp(`^${selectedResultName}-\\d+$`)
    return [...availableResults].filter((r) => pattern.test(r)).sort()
  }, [analysisConfig, selectedResultName, availableResults])

  const hasResult = selectedResultName
    ? availableResults.has(selectedResultName) || variantResults.length > 0
    : false

  // Semantic labels for variants (e.g. "Overall", "Protein-Membrane Interaction") from summary JSON
  const { data: analysisVariants } = useAnalysisVariants(
    experimentId,
    hasResult && analysisConfig?.hasVariants ? selectedResultName : null,
  )
  const variantLabelMap = useMemo(() => {
    const map = new Map<string, string>()
    for (const v of analysisVariants ?? []) map.set(v.analysis, v.name)
    return map
  }, [analysisVariants])
  const isRunningThis = activeJob?.analysis_name === selectedAnalysis

  // What to actually fetch and render: selected variant, falling back to summary
  const effectiveResultName = selectedVariant ?? selectedResultName

  const { data: analysisData, isLoading: isLoadingData } = useAnalysisData(
    experimentId,
    hasResult ? effectiveResultName : null,
  )

  const canSubmit = !!structureFile && !!coordsFile && !!selectedAnalysis && !activeJob && !submitAnalysis.isPending

  const handleCalculate = () => {
    if (!structureFile || !coordsFile || !selectedAnalysis) return
    submitAnalysis.mutate({
      analysis: selectedAnalysis,
      structure_file: structureFile.path,
      trajectory_file: coordsFile.path,
    })
  }

  // Most recent job for status display when no active job
  const lastJob = useMemo(() => {
    if (!jobs?.length) return null
    return jobs.reduce((latest, job) =>
      new Date(job.created_at) > new Date(latest.created_at) ? job : latest,
    )
  }, [jobs])

  const [showLogs, setShowLogs] = useState(false)
  const { data: jobLogs } = useAnalysisLogs(
    experimentId,
    showLogs && lastJob ? lastJob.id : null,
  )

  return (
    <div className="flex flex-col gap-3">
      {/* File selectors */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1.5">
          <Shapes className="text-muted-foreground h-4 w-4 shrink-0" />
          <FileSelector
            experimentId={experimentId}
            ext={STRUCTURE_FORMATS}
            title="Select structure file"
            onFileSelected={setStructureFile}
            className="w-52"
          />
        </div>
        {structureFile && (
          <div className="flex items-center gap-1.5">
            <Activity className="text-muted-foreground h-4 w-4 shrink-0" />
            <FileSelector
              experimentId={experimentId}
              ext={COORDINATE_FORMATS}
              title="Select trajectory file"
              onFileSelected={setCoordsFile}
              className="w-52"
            />
          </div>
        )}
      </div>

      {/* Analysis controls bar */}
      <div className="flex flex-wrap items-center gap-2">
        <Select value={selectedAnalysis ?? undefined} onValueChange={(v) => setSelectedAnalysis(v as AnalysisType)}>
          <SelectTrigger className="w-64">
            <SelectValue placeholder="Select analysis..." />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectLabel>Standard</SelectLabel>
              {AVAILABLE_ANALYSES.filter((a) => !a.requires).map((a) => (
                <SelectItem key={a.value} value={a.value}>
                  <span className="flex items-center gap-2">
                    {a.label}
                    {availableResults.has(a.resultName) && (
                      <span className="bg-primary/15 text-primary rounded px-1.5 py-0.5 text-[10px] font-medium">
                        ready
                      </span>
                    )}
                  </span>
                </SelectItem>
              ))}
            </SelectGroup>
            <SelectGroup>
              <SelectLabel>Membrane systems</SelectLabel>
              {AVAILABLE_ANALYSES.filter((a) => a.requires === "membrane").map((a) => (
                <SelectItem key={a.value} value={a.value}>
                  <span className="flex items-center gap-2">
                    {a.label}
                    {availableResults.has(a.resultName) && (
                      <span className="bg-primary/15 text-primary rounded px-1.5 py-0.5 text-[10px] font-medium">
                        ready
                      </span>
                    )}
                  </span>
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>

        {selectedAnalysis && (
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

        {/* Variant selector: shown when the analysis produced per-interaction numbered result files */}
        {hasResult && variantResults.length > 0 && (
          <Select
            value={selectedVariant ?? "__summary__"}
            onValueChange={(v) => setSelectedVariant(v === "__summary__" ? null : v)}
          >
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {availableResults.has(selectedResultName!) && (
                <SelectItem value="__summary__">All / Summary</SelectItem>
              )}
              {variantResults.map((v) => (
                <SelectItem key={v} value={v}>
                  {variantLabelMap.get(v) ?? getAnalysisLabel(v)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {/* Active job status badge */}
        {activeJob && (
          <span
            className={cn(
              "ml-auto inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
              statusBadgeClass(getJobStatusVariant(activeJob.status)),
            )}
          >
            <Loader2 className="h-3 w-3 animate-spin" />
            {JOB_STATUS_LABEL[activeJob.status]}
            {activeJob.analysis_name !== selectedAnalysis && (
              <span className="opacity-75">
                ({AVAILABLE_ANALYSES.find((a) => a.value === activeJob.analysis_name)?.label ?? activeJob.analysis_name})
              </span>
            )}
          </span>
        )}

        {/* Last job failed indicator */}
        {!activeJob && lastJob?.status === "ERROR" && (
          <>
            <span
              className={cn(
                "ml-auto inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
                statusBadgeClass("destructive"),
              )}
            >
              <CircleAlert className="h-3 w-3" />
              Failed
            </span>
            <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={() => setShowLogs((v) => !v)}>
              <Terminal className="mr-1 h-3 w-3" />
              {showLogs ? "Hide logs" : "View logs"}
            </Button>
          </>
        )}
      </div>

      {!structureFile && selectedAnalysis && !hasResult && (
        <p className="text-muted-foreground text-xs">Select structure and trajectory files to run analyses.</p>
      )}

      {/* Job logs (shown on demand after failure) */}
      {showLogs && (
        <pre className="bg-muted max-h-64 overflow-auto rounded-lg p-3 font-mono text-xs whitespace-pre-wrap">
          {jobLogs || "Loading logs..."}
        </pre>
      )}

      {/* Visualization area */}
      <div className="h-150">
        {!selectedAnalysis && (
          <div className="border-muted-foreground/25 bg-muted flex h-full flex-1 items-center justify-center rounded-lg border-2 border-dashed">
            <div className="space-y-2 text-center">
              <BarChart3 className="text-muted-foreground/50 mx-auto h-12 w-12" />
              <p className="text-muted-foreground text-sm">Select an analysis to view or calculate.</p>
            </div>
          </div>
        )}

        {selectedAnalysis && isRunningThis && (
          <div className="border-muted-foreground/25 bg-muted flex h-full flex-1 items-center justify-center rounded-lg border-2 border-dashed">
            <div className="space-y-2 text-center">
              <Loader2 className="text-muted-foreground/50 mx-auto h-12 w-12 animate-spin" />
              <p className="text-muted-foreground text-sm">Analysis is running...</p>
            </div>
          </div>
        )}

        {selectedAnalysis && !isRunningThis && !hasResult && (
          <div className="border-muted-foreground/25 bg-muted flex h-full flex-1 items-center justify-center rounded-lg border-2 border-dashed">
            <div className="space-y-2 text-center">
              <BarChart3 className="text-muted-foreground/50 mx-auto h-12 w-12" />
              <p className="text-muted-foreground text-sm">No results yet.</p>
              <p className="text-muted-foreground/75 text-xs">Click "Calculate" to run this analysis.</p>
            </div>
          </div>
        )}

        {selectedAnalysis && hasResult && isLoadingData && (
          <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            Loading analysis data...
          </div>
        )}

        {selectedAnalysis && hasResult && !isLoadingData && !!analysisData && effectiveResultName && (
          <AnalysisRenderer analysisName={effectiveResultName} data={analysisData as Analysis} />
        )}
      </div>

      {/* Footer metadata */}
      {selectedAnalysis && hasResult && !isLoadingData && (
        <>
          <Separator />
          <div className="text-muted-foreground text-xs">
            Experiment: {experimentId} · Analysis: {effectiveResultName}
          </div>
        </>
      )}
    </div>
  )
}

export default AnalysisPanel
