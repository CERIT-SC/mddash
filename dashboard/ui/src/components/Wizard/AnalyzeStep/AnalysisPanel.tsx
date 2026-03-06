import { useState } from "react"

import { BarChart3 } from "lucide-react"

import type { Analysis } from "@/util/analysis-types"
import { useAnalysisData, useAnalysisResults } from "@/hooks/use-analysis"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import AnalysisRenderer from "@/components/analysis/renderers"

interface AnalysisPanelProps {
  experimentId: string
}

const AnalysisPanel = ({ experimentId }: AnalysisPanelProps) => {
  const { data: results } = useAnalysisResults(experimentId)
  const [selectedAnalysis, setSelectedAnalysis] = useState<string | null>(null)
  const { data: analysisData, isLoading } = useAnalysisData(experimentId, selectedAnalysis)

  if (!results?.length) {
    return (
      <div className="border-muted-foreground/25 bg-muted flex h-full flex-1 items-center justify-center rounded-lg border-2 border-dashed">
        <div className="space-y-2 text-center">
          <BarChart3 className="text-muted-foreground/50 mx-auto h-12 w-12" />
          <p className="text-muted-foreground text-sm">No analysis results available.</p>
          <p className="text-muted-foreground/75 text-xs">Run an analysis to see visualizations here.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col gap-3">
      <Select value={selectedAnalysis ?? undefined} onValueChange={setSelectedAnalysis}>
        <SelectTrigger className="w-64">
          <SelectValue placeholder="Select analysis to view" />
        </SelectTrigger>
        <SelectContent>
          {results.map((r) => (
            <SelectItem key={r.name} value={r.name}>
              {r.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="min-h-125 flex-1">
        {isLoading && (
          <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
            Loading analysis data...
          </div>
        )}

        {!isLoading && selectedAnalysis && !!analysisData && (
          <AnalysisRenderer analysisName={selectedAnalysis} data={analysisData as Analysis} />
        )}

        {!isLoading && !selectedAnalysis && (
          <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
            Select an analysis from the dropdown above.
          </div>
        )}
      </div>
    </div>
  )
}

export default AnalysisPanel
