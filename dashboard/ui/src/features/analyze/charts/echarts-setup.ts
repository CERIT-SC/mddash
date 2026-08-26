import ReactEChartsCore from "echarts-for-react/lib/core"
import { BarChart, HeatmapChart, LineChart, ScatterChart } from "echarts/charts"
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components"
import * as echarts from "echarts/core"
import { CanvasRenderer } from "echarts/renderers"

// Register only the components we need
echarts.use([
  GridComponent,
  LegendComponent,
  TooltipComponent,
  DataZoomComponent,
  VisualMapComponent,
  TitleComponent,
  LineChart,
  BarChart,
  ScatterChart,
  HeatmapChart,
  CanvasRenderer,
])

export type { EChartsOption } from "echarts"
export { echarts }
export default ReactEChartsCore
