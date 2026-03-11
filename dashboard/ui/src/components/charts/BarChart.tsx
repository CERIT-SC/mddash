import React from "react"

import type { EChartsOption } from "./echarts-setup"
import EChartsBase from "./EChartsBase"

export interface BarSeries {
  name: string
  data: number[]
}

export interface BarChartProps {
  categories: string[]
  series: BarSeries[] // allow multiple series for comparisons
  horizontal?: boolean
  showLegend?: boolean
  height?: number | string
}

const BarChart: React.FC<BarChartProps> = ({
  categories,
  series,
  horizontal = false,
  showLegend = series.length > 1,
}) => {
  if (!series.length || !categories.length) {
    return (
      <div className="border-muted-foreground/40 text-muted-foreground flex h-full items-center justify-center rounded-lg border border-dashed px-4 text-sm">
        No bar chart data available.
      </div>
    )
  }

  const option: EChartsOption = {
    tooltip: { trigger: "axis" },
    legend: showLegend ? {} : undefined,
    grid: { left: 60, right: 20, top: 30, bottom: 40 },
    xAxis: horizontal ? { type: "value" } : { type: "category", data: categories },
    yAxis: horizontal ? { type: "category", data: categories } : { type: "value" },
    series: series.map((s) => ({
      name: s.name,
      type: "bar",
      data: s.data,
    })),
  }
  return <EChartsBase option={option} />
}

export default BarChart
