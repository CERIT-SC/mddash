import type { FC } from "react"
import { useMemo, useState } from "react"

import type { TMScoresAnalysis } from "@/util/analysis-types"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { downsampleSeries, formatStatValue, LineChart } from "@/components/charts"

type TMScoresChartProps = {
  data: TMScoresAnalysis
}

const TMScoresChart: FC<TMScoresChartProps> = ({ data }) => {
  const start: number = data.start ?? 0
  const step: number = data.step ?? 1
  const references = useMemo(() => Array.from(new Set(data.data.map((entry) => entry.reference))), [data.data])

  const [selectedReference, setSelectedReference] = useState<string>(references[0] ?? "")

  const filteredData = useMemo(() => {
    if (!selectedReference) return data.data
    return data.data.filter((entry) => entry.reference === selectedReference)
  }, [data.data, selectedReference])

  const series = useMemo(
    () =>
      filteredData.map((entry) => ({
        name: entry.group,
        data: downsampleSeries(entry.values, { start, step }),
      })),
    [filteredData, start, step]
  )

  const statsList = useMemo(
    () =>
      filteredData.map((entry) => {
        const values = entry.values
        if (values.length === 0) {
          return {
            label: entry.group,
            stats: { average: 0, stddev: 0, min: 0, max: 0 },
          } as const
        }
        const avg = values.reduce((sum, value) => sum + value, 0) / values.length
        const variance = values.reduce((sum, value) => sum + (value - avg) ** 2, 0) / values.length
        return {
          label: entry.group,
          stats: {
            average: avg,
            stddev: Math.sqrt(variance),
            min: Math.min(...values),
            max: Math.max(...values),
          },
        } as const
      }),
    [filteredData]
  )

  if (series.length === 0) {
    return (
      <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
        No TM-score data available.
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-6">
        {references.length > 1 && (
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
        )}

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

      <div className="min-h-0 flex-1">
        <LineChart series={series} xLabel="Frame" yLabel="TM-score" yScale showLegend />
      </div>
    </div>
  )
}

export default TMScoresChart
