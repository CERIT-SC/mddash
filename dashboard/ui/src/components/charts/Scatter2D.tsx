import React from "react"

import type { EChartsOption } from "./echarts-setup"
import EChartsBase from "./EChartsBase"

export interface ScatterPoint {
  x: number
  y: number
  c?: number | string // category or scalar for color
}

export interface Scatter2DProps {
  points: ScatterPoint[]
  xLabel?: string
  yLabel?: string
  colorBy?: "category" | "scalar" // interpret c as category or scalar
  categories?: string[] // for category legend order
}

const Scatter2D: React.FC<Scatter2DProps> = ({
  points,
  xLabel,
  yLabel,
  colorBy = "category",
  // categories,
}) => {
  if (!points.length) {
    return (
      <div className="border-muted-foreground/40 text-muted-foreground flex h-full items-center justify-center rounded-lg border border-dashed px-4 text-sm">
        No scatter data available.
      </div>
    )
  }

  const hasScalar = colorBy === "scalar" && points.some((p) => typeof p.c === "number")
  const option: EChartsOption = {
    tooltip: { trigger: "item" },
    grid: { left: 50, right: 20, top: 20, bottom: 50 },
    xAxis: { type: "value", name: xLabel },
    yAxis: { type: "value", name: yLabel },
    visualMap: hasScalar
      ? {
          min: Math.min(...(points.map((p) => (typeof p.c === "number" ? p.c : 0)) as number[])),
          max: Math.max(...(points.map((p) => (typeof p.c === "number" ? p.c : 0)) as number[])),
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
        data: points.map((p) => [p.x, p.y, p.c] as (number | string)[]),
        encode: { x: 0, y: 1, tooltip: [0, 1, 2] },
      },
    ],
  }
  return <EChartsBase option={option} style={{ width: "100%", height: "100%" }} />
}

export default Scatter2D
