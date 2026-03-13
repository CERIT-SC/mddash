import type { FC } from "react"
import { useMemo, useState } from "react"

import type { RMSDsAnalysis } from "@/util/analysis-types"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { downsampleSeries, formatStatValue, LineChart } from "@/components/charts"

type RMSDsChartProps = {
  data: RMSDsAnalysis
}

const RMSDsChart: FC<RMSDsChartProps> = ({ data }) => {
  const start: number = data.start ?? 0
  const step: number = data.step ?? 1

  // Extract unique references and groups
  const references = useMemo(() => Array.from(new Set(data.data.map((d) => d.reference))), [data.data])

  // State for selected reference and visible groups
  const [selectedReference, setSelectedReference] = useState<string>(references[0] ?? "")

  // Filter data by selected reference
  const filteredData = useMemo(
    () => data.data.filter((d) => d.reference === selectedReference),
    [data.data, selectedReference]
  )

  // Build series for LineChart with downsampling
  const series = useMemo(
    () =>
      filteredData.map((d) => ({
        name: d.group,
        data: downsampleSeries(d.values, { start, step }),
      })),
    [filteredData, start, step]
  )

  // Compute stats for each series
  const statsList = useMemo(
    () =>
      filteredData.map((d) => {
        const values = d.values
        if (values.length === 0) {
          return { label: d.group, stats: { average: 0, stddev: 0, min: 0, max: 0 } } as const
        }
        const avg = values.reduce((a, b) => a + b, 0) / values.length
        const variance = values.reduce((sum, val) => sum + (val - avg) ** 2, 0) / values.length
        const stddev = Math.sqrt(variance)
        const min = Math.min(...values)
        const max = Math.max(...values)
        return {
          label: d.group,
          stats: { average: avg, stddev, min, max },
        } as const
      }),
    [filteredData]
  )

  if (series.length === 0) {
    return <div className="text-muted-foreground flex h-full items-center justify-center">No groups selected</div>
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      {/* Reference selector and Stats in one row */}
      <div className="flex flex-wrap items-center gap-6">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Reference:</span>
          <Select value={selectedReference} onValueChange={setSelectedReference}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {references.map((ref) => (
                <SelectItem key={ref} value={ref}>
                  {ref}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Stats */}
        {statsList.length > 0 && (
          <div className="text-muted-foreground flex flex-wrap items-center gap-x-6 gap-y-1 text-xs">
            {statsList.map(({ label, stats }) => (
              <div key={label} className="flex items-center gap-3">
                <span className="text-foreground/80 font-medium">{label}</span>
                <span>Avg: {formatStatValue(stats.average)}</span>
                <span>Std: {formatStatValue(stats.stddev)}</span>
                <span>Min: {formatStatValue(stats.min)}</span>
                <span>Max: {formatStatValue(stats.max)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Chart */}
      <div className="min-h-0 flex-1">
        <LineChart series={series} xLabel="Frame" yLabel="RMSD (nm)" yScale showLegend />
      </div>
    </div>
  )
}

export default RMSDsChart
