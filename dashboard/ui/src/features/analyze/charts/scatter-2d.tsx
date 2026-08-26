import React from "react"

import EChartsBase from "./echarts-base"
import type { EChartsOption } from "./echarts-setup"

export interface ScatterPoint {
  x: number
  y: number
  /** Optional scalar driving the visualMap color. */
  c?: number
}

export interface Scatter2DProps {
  points: ScatterPoint[]
  xLabel?: string
  yLabel?: string
}

const Scatter2D: React.FC<Scatter2DProps> = ({ points, xLabel, yLabel }) => {
  if (!points.length) {
    return (
      <div className="border-border text-text-muted flex h-full items-center justify-center rounded-lg border border-dashed px-4 text-sm">
        No scatter data available.
      </div>
    )
  }

  const colorValues = points.map((p) => p.c).filter((c): c is number => typeof c === "number")
  const hasScalar = colorValues.length > 0
  const option: EChartsOption = {
    tooltip: { trigger: "item" },
    grid: { left: 50, right: 20, top: 20, bottom: 50 },
    xAxis: { type: "value", name: xLabel },
    yAxis: { type: "value", name: yLabel },
    visualMap: hasScalar
      ? {
          min: Math.min(...colorValues),
          max: Math.max(...colorValues),
          calculable: true,
          orient: "horizontal",
          left: "center",
          bottom: 0,
        }
      : undefined,
    series: [
      {
        type: "scatter",
        symbolSize: 5,
        data: points.map((p) => [p.x, p.y, p.c] as (number | undefined)[]),
        encode: { x: 0, y: 1, tooltip: [0, 1, 2] },
      },
    ],
  }
  return <EChartsBase option={option} />
}

export default Scatter2D
