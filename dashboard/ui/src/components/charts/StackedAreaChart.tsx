import React from "react"

import type { EChartsOption } from "./echarts-setup"
import EChartsBase from "./EChartsBase"

export interface StackedSeries {
  name: string
  data: Array<[number, number]> // [x, y]
}

export interface StackedAreaChartProps {
  series: StackedSeries[]
  xLabel?: string
  yLabel?: string
  showLegend?: boolean
  stackId?: string
  height?: number | string
}

const StackedAreaChart: React.FC<StackedAreaChartProps> = ({
  series,
  xLabel,
  yLabel,
  showLegend = true,
  stackId = "total",
}) => {
  if (!series.length) {
    return (
      <div className="border-muted-foreground/40 text-muted-foreground flex h-full items-center justify-center rounded-lg border border-dashed px-4 text-sm">
        No stacked data available.
      </div>
    )
  }

  const option: EChartsOption = {
    tooltip: { trigger: "axis" },
    legend: showLegend ? {} : undefined,
    grid: { left: 40, right: 20, top: 30, bottom: 40 },
    xAxis: { type: "value", name: xLabel },
    yAxis: { type: "value", name: yLabel },
    dataZoom: [{ type: "inside" }, { type: "slider" }],
    series: series.map((s) => ({
      name: s.name,
      type: "line",
      stack: stackId,
      showSymbol: false,
      areaStyle: {},
      data: s.data,
    })),
  }

  return <EChartsBase option={option} />
}

export default StackedAreaChart
