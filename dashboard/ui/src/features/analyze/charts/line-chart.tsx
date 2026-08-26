import React from "react"

import EChartsBase from "./echarts-base"
import type { EChartsOption } from "./echarts-setup"

export interface LineSeries {
  name: string
  data: Array<[number, number]> // [x, y]
}

export interface LineChartProps {
  series: LineSeries[]
  xLabel?: string
  yLabel?: string
  showLegend?: boolean
  area?: boolean // render with area under curve
  // Axis scaling: when true, axis won't force-include zero; focuses on data range
  xScale?: boolean
  yScale?: boolean
  // Optional explicit axis bounds
  xMin?: number
  xMax?: number
  yMin?: number
  yMax?: number
  // DataZoom (brush) slider positioning
  zoomSliderBottom?: number // distance from bottom (px), default 8
  zoomSliderHeight?: number // slider height (px), default 26
  height?: number | string
}

const LineChart: React.FC<LineChartProps> = ({
  series,
  xLabel,
  yLabel,
  showLegend = true,
  area = false,
  xScale = false,
  yScale = false,
  xMin,
  xMax,
  height,
  yMin,
  yMax,
  zoomSliderBottom = 10,
  zoomSliderHeight = 26,
}) => {
  if (!series.length) {
    return (
      <div className="border-border text-text-muted flex h-full items-center justify-center rounded-lg border border-dashed px-4 text-sm">
        No timeseries data available.
      </div>
    )
  }

  // Compute bottom padding so x-axis labels, axis name, and slider don't get clipped
  const baseBottom = 28 // room for tick labels
  const xNameExtra = xLabel ? 20 : 0 // additional space for axis name
  const sliderExtra = zoomSliderBottom + zoomSliderHeight + 6 // slider + gap
  const gridBottom = baseBottom + xNameExtra + sliderExtra

  const option: EChartsOption = {
    tooltip: { trigger: "axis" },
    legend: showLegend ? {} : undefined,
    grid: { left: 40, right: 20, top: 30, bottom: gridBottom },
    xAxis: {
      type: "value",
      name: xLabel,
      nameLocation: "middle",
      nameGap: 30,
      scale: xScale,
      min: xMin,
      max: xMax,
    },
    yAxis: {
      type: "value",
      name: yLabel,
      nameLocation: "end",
      scale: yScale,
      min: yMin,
      max: yMax,
    },
    dataZoom: [{ type: "inside" }, { type: "slider", bottom: zoomSliderBottom, height: zoomSliderHeight }],
    series: series.map((s) => ({
      name: s.name,
      type: "line",
      showSymbol: false,
      smooth: false,
      areaStyle: area ? {} : undefined,
      data: s.data,
    })),
  }

  return <EChartsBase option={option} height={height} />
}

export default LineChart
