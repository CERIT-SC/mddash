import { useState } from "react"

import { Loader2, Play } from "lucide-react"

import { statusBadgeClass } from "@/lib/status"
import { AVAILABLE_ANALYSES, type AnalysisType } from "@/util/analysis-types"
import { getJobStatusVariant } from "@/util/types"
import type { FileOption } from "@/util/types"
import { useAnalysisJobs, useSubmitAnalysis } from "@/hooks/use-analysis"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

interface AnalysisControlsProps {
  experimentId: string
  structureFile: FileOption | null
  coordsFile: FileOption | null
}

const AnalysisControls = ({ experimentId, structureFile, coordsFile }: AnalysisControlsProps) => {
  const { data: jobs } = useAnalysisJobs(experimentId)
  const submitAnalysis = useSubmitAnalysis(experimentId)
  const [selectedAnalysis, setSelectedAnalysis] = useState<AnalysisType | null>(null)

  const latestJob = jobs?.length ? jobs[jobs.length - 1] : null
  const isActive = latestJob?.status === "RUNNING" || latestJob?.status === "PENDING"
  const canSubmit = !!structureFile && !!coordsFile && !!selectedAnalysis && !isActive && !submitAnalysis.isPending

  const handleSubmit = () => {
    if (!structureFile || !coordsFile || !selectedAnalysis) return
    submitAnalysis.mutate({
      analysis: selectedAnalysis,
      structure_file: structureFile.path,
      trajectory_file: coordsFile.path,
    })
  }

  return (
    <div className="flex flex-col gap-2">
      <Select value={selectedAnalysis ?? undefined} onValueChange={(v) => setSelectedAnalysis(v as AnalysisType)}>
        <SelectTrigger className="w-full">
          <SelectValue placeholder="Select analysis..." />
        </SelectTrigger>
        <SelectContent>
          {AVAILABLE_ANALYSES.map((a) => (
            <SelectItem key={a.value} value={a.value}>
              {a.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="flex items-center gap-2">
        <Button size="sm" onClick={handleSubmit} disabled={!canSubmit}>
          {isActive ? (
            <>
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              Running...
            </>
          ) : (
            <>
              <Play className="mr-1 h-3.5 w-3.5" />
              Run
            </>
          )}
        </Button>

        {latestJob && (
          <Badge className={statusBadgeClass(getJobStatusVariant(latestJob.status))}>
            {latestJob.analysis_name} — {latestJob.status}
          </Badge>
        )}
      </div>

      {!structureFile && <p className="text-muted-foreground text-xs">Select structure and trajectory files first.</p>}

      {structureFile && !coordsFile && (
        <p className="text-muted-foreground text-xs">Select a trajectory file to enable analysis.</p>
      )}
    </div>
  )
}

export default AnalysisControls
