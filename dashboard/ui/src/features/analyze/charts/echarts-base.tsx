import React from "react"

import ReactEChartsCore, { echarts, type EChartsOption } from "./echarts-setup"

interface EChartsBaseProps {
  option: EChartsOption
  className?: string
  style?: React.CSSProperties
  height?: number | string
  // Allow passing through opts like renderer, width/height handling
  opts?: {
    renderer?: "canvas" | "svg"
    height?: number | "auto" | null
    width?: number | "auto" | null
    locale?: string
  }
}

const EChartsBase: React.FC<EChartsBaseProps> = ({ option, className, style, opts, height = 400 }) => {
  const resolvedHeight = typeof height === "number" ? `${height}px` : height
  return (
    <ReactEChartsCore
      echarts={echarts}
      option={option}
      className={className}
      style={{ width: "100%", height: resolvedHeight, ...style }}
      opts={opts}
      notMerge={true}
      lazyUpdate={true}
    />
  )
}

export default EChartsBase
