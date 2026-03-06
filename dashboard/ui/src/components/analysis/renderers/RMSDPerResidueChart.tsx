import { useEffect, useMemo, useState, type FC } from "react"

import type { RMSDPerResidueAnalysis } from "@/util/analysis-types"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { buildTimeSeries, formatStatValue, LineChart } from "@/components/charts"

type RMSDPerResidueChartProps = {
  data: RMSDPerResidueAnalysis
}

const RMSDPerResidueChart: FC<RMSDPerResidueChartProps> = ({ data }) => {
  const entries = useMemo(() => data.data ?? [], [data])
  const datasetNames = entries.map((entry) => entry.name)
  const [selectedDataset, setSelectedDataset] = useState<string>("")
  const frameStep = data.step ?? 1

  useEffect(() => {
    if (!entries.length) return
    const fallback = entries[0]?.name ?? ""
    if (!selectedDataset || !entries.some((entry) => entry.name === selectedDataset)) {
      setSelectedDataset(fallback)
    }
  }, [entries, selectedDataset])

  const activeEntry = useMemo(() => {
    if (!entries.length) return undefined
    return entries.find((entry) => entry.name === selectedDataset) ?? entries[0]
  }, [entries, selectedDataset])

  const chartSeries = activeEntry
    ? [
        {
          name: activeEntry.name,
          data: buildTimeSeries(activeEntry.rmsds, {
            start: 0,
            step: frameStep,
          }),
        },
      ]
    : []

  const stats = useMemo(() => {
    if (!activeEntry) return undefined
    const values = activeEntry.rmsds
    if (!values.length) return undefined
    const avg = values.reduce((sum, value) => sum + value, 0) / values.length
    const variance = values.reduce((sum, value) => sum + (value - avg) ** 2, 0) / values.length
    return {
      average: avg,
      stddev: Math.sqrt(variance),
      min: Math.min(...values),
      max: Math.max(...values),
    }
  }, [activeEntry])

  if (!chartSeries.length) {
    return (
      <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
        No RMSD per residue data available.
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-4">
        {datasetNames.length > 1 && (
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">Residue:</span>
            <Select value={activeEntry?.name ?? selectedDataset} onValueChange={setSelectedDataset}>
              <SelectTrigger className="w-48">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {datasetNames.map((name) => (
                  <SelectItem key={name} value={name}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {stats && (
          <div className="text-muted-foreground flex flex-wrap items-center gap-x-6 gap-y-1 text-xs">
            <div className="flex items-center gap-3">
              <span className="text-foreground/80 font-medium">{activeEntry?.name}</span>
              <span>Avg: {formatStatValue(stats.average)}</span>
              <span>Std: {formatStatValue(stats.stddev)}</span>
              <span>Min: {formatStatValue(stats.min)}</span>
              <span>Max: {formatStatValue(stats.max)}</span>
            </div>
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1">
        <LineChart
          series={chartSeries}
          xLabel={frameStep !== 1 ? `Frame (step ${frameStep})` : "Frame index"}
          yLabel="RMSD (nm)"
          showLegend={false}
          yScale
        />
      </div>
    </div>
  )
}

export default RMSDPerResidueChart
