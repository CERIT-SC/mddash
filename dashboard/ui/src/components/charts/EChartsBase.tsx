import React from "react"

import ReactEChartsCore, { echarts, type EChartsOption } from "./echarts-setup"

export interface EChartsBaseProps {
  option: EChartsOption
  className?: string
  style?: React.CSSProperties
  // Allow passing through opts like renderer, width/height handling
  opts?: {
    renderer?: "canvas" | "svg"
    height?: number | "auto" | null
    width?: number | "auto" | null
    locale?: string
  }
}

const EChartsBase: React.FC<EChartsBaseProps> = ({ option, className, style, opts }) => {
  return (
    <ReactEChartsCore
      echarts={echarts}
      option={option}
      className={className}
      style={style}
      opts={opts}
      notMerge={true}
      lazyUpdate={true}
    />
  )
}

export default EChartsBase
