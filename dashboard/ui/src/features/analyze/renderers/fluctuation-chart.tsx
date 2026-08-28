import type { FC } from "react"

import type { FluctuationAnalysis } from "../analysis-types"
import { formatStatValue, LineChart, statToSeries } from "../charts"

type FluctuationChartProps = {
  data: FluctuationAnalysis
}

const FluctuationChart: FC<FluctuationChartProps> = ({ data }) => {
  const start: number = data.start ?? 0
  const step: number = data.step ?? 1
  const rmsfSeries = statToSeries(data.y?.rmsf, {
    name: "RMSF",
    start,
    step,
  })

  if (!rmsfSeries) return null

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="text-text-muted flex justify-center gap-6 text-xs">
        <div className="flex items-center gap-3">
          <span className="text-text/80 font-medium">RMSF</span>
          <span>Avg: {formatStatValue(rmsfSeries.stats.average)}</span>
          <span>Std: {formatStatValue(rmsfSeries.stats.stddev)}</span>
          <span>Min: {formatStatValue(rmsfSeries.stats.min)}</span>
          <span>Max: {formatStatValue(rmsfSeries.stats.max)}</span>
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <LineChart
          series={[{ name: rmsfSeries.name, data: rmsfSeries.data }]}
          xLabel="Residue index"
          yLabel="RMSF (nm)"
          yScale
        />
      </div>
    </div>
  )
}

export default FluctuationChart
