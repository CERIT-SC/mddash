import React from "react"

import type { EChartsOption } from "./echarts-setup"
import EChartsBase from "./EChartsBase"

export type TooltipContext = {
  params: unknown
  value: number
  xIndex: number
  yIndex: number
  xLabel?: string
  yLabel?: string
}

export interface HeatmapMatrixProps {
  // Data as [xIndex, yIndex, value]
  data: Array<[number, number, number]>
  xLabels?: string[]
  yLabels?: string[]
  title?: string
  enableFilter?: boolean
  valueRange?: {
    min?: number
    max?: number
  }
  tooltipFormatter?: (context: TooltipContext) => string
}

const HeatmapMatrix: React.FC<HeatmapMatrixProps> = ({
  data,
  xLabels,
  yLabels,
  title,
  enableFilter = true,
  valueRange,
  tooltipFormatter,
}) => {
  if (data.length === 0) {
    return (
      <div className="border-muted-foreground/40 text-muted-foreground flex h-full items-center justify-center rounded-lg border border-dashed px-4 text-sm">
        No heatmap data available.
      </div>
    )
  }

  const values = data.map((d) => d[2])
  const computedMin = Math.min(...values)
  const computedMax = Math.max(...values)
  const minValue = typeof valueRange?.min === "number" && Number.isFinite(valueRange.min) ? valueRange.min : computedMin
  const maxValue = typeof valueRange?.max === "number" && Number.isFinite(valueRange.max) ? valueRange.max : computedMax

  const defaultTooltip = (context: TooltipContext) => {
    const xLabel = context.xLabel ?? `Col ${context.xIndex + 1}`
    const yLabel = context.yLabel ?? `Row ${context.yIndex + 1}`
    const formattedValue = Number.isFinite(context.value) ? context.value.toFixed(2) : String(context.value)
    return `<div><strong>${yLabel}</strong><br/>${xLabel}: ${formattedValue}</div>`
  }

  const buildTooltipContext = (params: unknown): TooltipContext => {
    if (params && typeof params === "object" && Array.isArray((params as { value?: unknown }).value)) {
      const tuple = (params as { value: unknown[] }).value
      const [xIdxRaw, yIdxRaw, rawValue] = tuple
      const xIndex = Number.isFinite(xIdxRaw as number) ? Number(xIdxRaw) : 0
      const yIndex = Number.isFinite(yIdxRaw as number) ? Number(yIdxRaw) : 0
      const numericValue = typeof rawValue === "number" && Number.isFinite(rawValue) ? rawValue : Number(rawValue)
      const value = Number.isFinite(numericValue) ? numericValue : 0
      return {
        params,
        value,
        xIndex,
        yIndex,
        xLabel: xLabels?.[xIndex],
        yLabel: yLabels?.[yIndex],
      }
    }

    return {
      params,
      value: 0,
      xIndex: 0,
      yIndex: 0,
      xLabel: xLabels?.[0],
      yLabel: yLabels?.[0],
    }
  }

  const option: EChartsOption = {
    title: title ? { text: title } : undefined,
    tooltip: {
      position: "top",
      // Keep tooltip within chart bounds to avoid page overflow
      confine: true,
      formatter: (param) => {
        const context = buildTooltipContext(param)
        return tooltipFormatter ? tooltipFormatter(context) : defaultTooltip(context)
      },
    },
    grid: { height: "85%", width: "90%", left: "5%", top: "5%" },
    xAxis: {
      type: "category",
      data: xLabels ?? [],
      splitArea: { show: true },
      axisLabel: { show: !!xLabels },
    },
    yAxis: {
      type: "category",
      data: yLabels ?? [],
      splitArea: { show: true },
      axisLabel: { show: !!yLabels },
    },
    visualMap: {
      min: minValue,
      max: maxValue,
      calculable: enableFilter,
      // Avoid continuous re-render while dragging handles
      realtime: false,
      // Hovering the slider was triggering full heatmap highlights
      hoverLink: false,
      orient: "horizontal",
      left: "center",
      bottom: 0,
    },
    series: [
      {
        name: "matrix",
        type: "heatmap",
        data,
        emphasis: {
          itemStyle: { shadowBlur: 10, shadowColor: "rgba(0, 0, 0, 0.5)" },
        },
        progressive: 8000,
        progressiveThreshold: 20000,
        animation: false,
      },
    ],
  }
  return <EChartsBase option={option} style={{ width: "100%", height: "100%" }} opts={{ renderer: "canvas" }} />
}

export default HeatmapMatrix
