import type { FC } from "react"

import type { RMSDAnalysis } from "../analysis-types"
import { formatStatValue, LineChart, statToSeries } from "../charts"

type RMSDChartProps = {
  data: RMSDAnalysis
  xLabel?: string
  yLabel?: string
}

const RMSDChart: FC<RMSDChartProps> = ({ data, xLabel = "Frame", yLabel = "RMSD (nm)" }) => {
  const start = 0
  const step: number = data.step ?? 1
  const rmsdSeries = statToSeries(data.y?.rmsd, {
    name: "RMSD",
    start,
    step,
  })

  if (!rmsdSeries) return null

  const series = [
    {
      name: rmsdSeries.name,
      data: rmsdSeries.data,
    },
  ]

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="text-text-muted flex justify-center gap-6 text-xs">
        <div className="flex items-center gap-3">
          <span className="text-text/80 font-medium">RMSD</span>
          <span>Avg: {formatStatValue(rmsdSeries.stats.average)}</span>
          <span>Std: {formatStatValue(rmsdSeries.stats.stddev)}</span>
          <span>Min: {formatStatValue(rmsdSeries.stats.min)}</span>
          <span>Max: {formatStatValue(rmsdSeries.stats.max)}</span>
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <LineChart series={series} xLabel={xLabel} yLabel={yLabel} />
      </div>
    </div>
  )
}

export default RMSDChart
