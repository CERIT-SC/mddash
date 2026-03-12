import { useEffect, useMemo, useRef, useState } from "react"

import { useQueryClient } from "@tanstack/react-query"
import {
  Activity,
  BarChart3,
  CircleAlert,
  FileKey,
  Info,
  Loader2,
  Play,
  RefreshCw,
  Shapes,
  Terminal,
} from "lucide-react"

import { statusBadgeClass } from "@/lib/status"
import { cn } from "@/lib/utils"
import { AVAILABLE_ANALYSES, type Analysis, type AnalysisType } from "@/util/analysis-types"
import { getAnalysisLabel } from "@/util/analysis-utils"
import type { FileOption } from "@/util/types"
import { getJobStatusVariant } from "@/util/types"
import {
  useAnalysisData,
  useAnalysisJobs,
  useAnalysisLogs,
  useAnalysisVariants,
  useSubmitAnalysis,
} from "@/hooks/use-analysis"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import AnalysisRenderer from "@/components/analysis/renderers"
import FileSelector from "@/components/FileSelector"
import LogsView from "@/components/LogsView"

interface AnalysisPanelProps {
  experimentId: string
}

const STRUCTURE_FORMATS = ["pdb", "gro"]
const COORDINATE_FORMATS = ["xtc", "trr"]
const TOPOLOGY_FORMATS = ["tpr", "top", "prmtop", "psf"]

const AnalysisPanel = ({ experimentId }: AnalysisPanelProps) => {
  const queryClient = useQueryClient()
  const [structureFile, setStructureFile] = useState<FileOption | null>(null)
  const [coordsFile, setCoordsFile] = useState<FileOption | null>(null)
  const [topologyFile, setTopologyFile] = useState<FileOption | null>(null)

  useEffect(() => {
    if (!structureFile) setCoordsFile(null)
  }, [structureFile])

  const { data: jobs } = useAnalysisJobs(experimentId)
  const activeJob = useMemo(() => jobs?.find((j) => j.status === "RUNNING" || j.status === "PENDING"), [jobs])

  // Invalidate cached result data when a job finishes so charts always show fresh output.
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
  const [selectedAnalysis, setSelectedAnalysis] = useState<AnalysisType | null>(null)
  const [selectedVariant, setSelectedVariant] = useState<string | null>(null)

  useEffect(() => {
    setSelectedVariant(null)
    setTopologyFile(null)
  }, [selectedAnalysis])

  const availableResults = useMemo(() => new Set(jobs?.flatMap((j) => j.results) ?? []), [jobs])

  const analysisConfig = useMemo(() => AVAILABLE_ANALYSES.find((a) => a.value === selectedAnalysis), [selectedAnalysis])
  const selectedResultName = analysisConfig?.resultName ?? null

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
  const isRunningThis = activeJob?.analysis_name === selectedAnalysis

  // For hasVariants analyses the base file is the variant index — never fetch or render it.
  const effectiveResultName = analysisConfig?.hasVariants ? selectedVariant : (selectedVariant ?? selectedResultName)

  const { data: analysisData, isLoading: isLoadingData } = useAnalysisData(
    experimentId,
    hasResult ? effectiveResultName : null
  )

  const needsTopology = analysisConfig?.requires === "topology"
  const canSubmit =
    !!structureFile &&
    !!coordsFile &&
    !!selectedAnalysis &&
    (!needsTopology || !!topologyFile) &&
    !activeJob &&
    !submitAnalysis.isPending

  const handleCalculate = () => {
    if (!structureFile || !coordsFile || !selectedAnalysis) return
    submitAnalysis.mutate({
      analysis: selectedAnalysis,
      structure_file: structureFile.path,
      trajectory_file: coordsFile.path,
      ...(needsTopology && topologyFile && { topology_file: topologyFile.path }),
    })
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

  const [showLogs, setShowLogs] = useState(false)
  useEffect(() => {
    if (!activeJob) setShowLogs(false)
  }, [activeJob])
  const logJobId = showLogs ? (activeJob?.id ?? lastJob?.id ?? null) : null
  const { data: jobLogs } = useAnalysisLogs(experimentId, logJobId, !!activeJob)

  return (
    <div className="flex flex-col gap-3">
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
        {needsTopology && (
          <div className="flex items-center gap-1.5">
            <FileKey className="text-muted-foreground h-4 w-4 shrink-0" />
            <FileSelector
              experimentId={experimentId}
              ext={TOPOLOGY_FORMATS}
              title="Select topology file"
              onFileSelected={setTopologyFile}
              className="w-52"
            />
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Select value={selectedAnalysis ?? undefined} onValueChange={(v) => setSelectedAnalysis(v as AnalysisType)}>
          <SelectTrigger className="w-64">
            <SelectValue placeholder="Select analysis..." />
          </SelectTrigger>
          <SelectContent>
            {AVAILABLE_ANALYSES.map((a) => (
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

        {/* "All / Summary" is never shown — the base file is the variant index, not independently renderable. */}
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
              {activeJob.analysis_name !== selectedAnalysis && (
                <span className="opacity-75">
                  (
                  {AVAILABLE_ANALYSES.find((a) => a.value === activeJob.analysis_name)?.label ??
                    activeJob.analysis_name}
                  )
                </span>
              )}
            </span>
            <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={() => setShowLogs((v) => !v)}>
              <Terminal className="mr-1 h-3 w-3" />
              {showLogs ? "Hide logs" : "View logs"}
            </Button>
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

      {showLogs && <LogsView logs={jobLogs ?? ""} />}

      <div>
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
          <div className="border-muted-foreground/25 bg-muted flex h-full flex-1 items-center justify-center rounded-lg border-2 border-dashed py-5">
            {completedWithNoResult ? (
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
                <p className="text-muted-foreground/75 text-xs">Click "Calculate" to run this analysis.</p>
              </div>
            )}
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
    </div>
  )
}

export default AnalysisPanel
