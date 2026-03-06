import { useMemo, useState, type FC } from "react"

import type { DensityProfileAnalysis } from "@/util/analysis-types"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { LineChart } from "@/components/charts"
import type { LineSeries } from "@/components/charts/LineChart"

const METRIC_OPTIONS = [
  { key: "number", label: "Number density", unit: "#/A^3" },
  { key: "mass", label: "Mass density", unit: "amu/A^3" },
  { key: "charge", label: "Charge density", unit: "e/A^3" },
  { key: "electron", label: "Electron density", unit: "electron/A^3" },
] as const

type MetricKey = (typeof METRIC_OPTIONS)[number]["key"]
type ValueMode = "density" | "stdv"

type ComponentSeries = {
  id: string
  name: string
  selectionCount: number
  number: { dens: number[]; stdv: number[] }
  mass: { dens: number[]; stdv: number[] }
  charge: { dens: number[]; stdv: number[] }
  electron: { dens: number[]; stdv: number[] }
}

const sanitizeNumericArray = (values: unknown): number[] => {
  if (!Array.isArray(values)) return []
  return values
    .map((value) => (typeof value === "number" && Number.isFinite(value) ? value : null))
    .filter((value): value is number => value !== null)
}

const buildSeries = (label: string, xValues: number[], yValues: number[]): LineSeries | undefined => {
  if (!xValues.length || !yValues.length) return undefined
  const limit = Math.min(xValues.length, yValues.length)
  const data: Array<[number, number]> = []
  for (let i = 0; i < limit; i += 1) {
    const x = xValues[i]
    const y = yValues[i]
    if (Number.isFinite(x) && Number.isFinite(y)) {
      data.push([x, y])
    }
  }
  return data.length ? { name: label, data } : undefined
}

const DensityProfilePanel: FC<{ data: DensityProfileAnalysis }> = ({ data }) => {
  const [metric, setMetric] = useState<MetricKey>("number")
  const [valueMode, setValueMode] = useState<ValueMode>("density")

  const zPositions = useMemo(() => sanitizeNumericArray(data?.data?.z), [data?.data?.z])

  const components = useMemo<ComponentSeries[]>(() => {
    if (!data?.data || !Array.isArray(data.data.comps)) return []
    return data.data.comps.map((component, index) => {
      const name =
        typeof component?.name === "string" && component.name.trim() ? component.name.trim() : `Component ${index + 1}`
      const selectionCount = Array.isArray(component?.selection) ? component.selection.length : 0
      const toMetric = (payload: unknown) => ({
        dens: sanitizeNumericArray((payload as { dens?: unknown })?.dens),
        stdv: sanitizeNumericArray((payload as { stdv?: unknown })?.stdv),
      })
      return {
        id: `${index}`,
        name,
        selectionCount,
        number: toMetric(component?.number),
        mass: toMetric(component?.mass),
        charge: toMetric(component?.charge),
        electron: toMetric(component?.electron),
      }
    })
  }, [data])

  const selectedMetric = METRIC_OPTIONS.find((option) => option.key === metric)

  const chartSeries = useMemo(() => {
    const series: LineSeries[] = []
    components.forEach((component) => {
      const metricPayload = component[metric]
      const values = valueMode === "density" ? metricPayload.dens : metricPayload.stdv
      const subSeries = buildSeries(component.name, zPositions, values)
      if (subSeries) {
        series.push(subSeries)
      }
    })
    return series
  }, [components, metric, valueMode, zPositions])

  const peakLookup = useMemo(() => {
    const map = new Map<string, string>()
    components.forEach((component) => {
      const metricPayload = component[metric]
      const values = valueMode === "density" ? metricPayload.dens : metricPayload.stdv
      if (!values.length) {
        map.set(component.id, "N/A")
        return
      }
      const magnitude = values.reduce((max, current) => Math.max(max, Math.abs(current)), 0)
      map.set(component.id, Number.isFinite(magnitude) ? magnitude.toFixed(3) : "N/A")
    })
    return map
  }, [components, metric, valueMode])

  if (!components.length || !zPositions.length) {
    return (
      <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
        No density profile analysis data available.
      </div>
    )
  }

  const metricLabel = selectedMetric?.label ?? "Density"
  const modeLabel = valueMode === "density" ? "Density" : "Std dev"
  const yAxisLabel = valueMode === "density" ? metricLabel : `${metricLabel} std dev`

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium">Density profiles</p>
          <p className="text-muted-foreground text-xs">
            Toggle between number, mass, charge, or electron density to compare leaflet components.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Select value={metric} onValueChange={(value) => setMetric(value as MetricKey)}>
            <SelectTrigger className="h-8 w-48 text-xs">
              <SelectValue placeholder="Metric" />
            </SelectTrigger>
            <SelectContent>
              {METRIC_OPTIONS.map((option) => (
                <SelectItem key={option.key} value={option.key}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={valueMode} onValueChange={(value) => setValueMode(value as ValueMode)}>
            <SelectTrigger className="h-8 w-40 text-xs">
              <SelectValue placeholder="Value" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="density">Density</SelectItem>
              <SelectItem value="stdv">Std dev</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="border-border/70 rounded-md border p-3">
          <p className="text-muted-foreground/80 text-[11px] tracking-wide uppercase">Samples</p>
          <p className="text-lg font-semibold">{zPositions.length}</p>
        </div>
        <div className="border-border/70 rounded-md border p-3">
          <p className="text-muted-foreground/80 text-[11px] tracking-wide uppercase">Components</p>
          <p className="text-lg font-semibold">{components.length}</p>
        </div>
        <div className="border-border/70 rounded-md border p-3">
          <p className="text-muted-foreground/80 text-[11px] tracking-wide uppercase">Metric</p>
          <p className="text-lg font-semibold">{metricLabel}</p>
        </div>
        <div className="border-border/70 rounded-md border p-3">
          <p className="text-muted-foreground/80 text-[11px] tracking-wide uppercase">Mode</p>
          <p className="text-lg font-semibold">{modeLabel}</p>
        </div>
      </div>

      <div className="border-border/60 flex min-h-80 flex-col rounded-lg border p-4">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Profile along membrane normal</p>
            <p className="text-muted-foreground text-xs">
              Z-axis samples ({zPositions.length}) plotted against {modeLabel.toLowerCase()}.
            </p>
          </div>
          {selectedMetric?.unit && <p className="text-muted-foreground text-xs">Units: {selectedMetric.unit}</p>}
        </div>
        <div className="min-h-65 flex-1">
          {chartSeries.length ? (
            <LineChart series={chartSeries} xLabel="Z (Angstrom)" yLabel={yAxisLabel} showLegend yScale />
          ) : (
            <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
              No matching density data available for the selected metric.
            </div>
          )}
        </div>
      </div>

      <div className="border-border/60 rounded-lg border p-4">
        <p className="text-muted-foreground mb-3 text-xs tracking-wide uppercase">Components overview</p>
        <div className="space-y-3">
          {components.map((component) => {
            const peakValue = peakLookup.get(component.id) ?? "N/A"
            const suffix = peakValue !== "N/A" && selectedMetric?.unit ? ` ${selectedMetric.unit}` : ""
            return (
              <div
                key={component.id}
                className="border-border/50 flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <p className="text-sm font-semibold">{component.name}</p>
                  <p className="text-muted-foreground text-xs">Selection size: {component.selectionCount || "N/A"}</p>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-muted-foreground text-xs">
                    Peak {modeLabel.toLowerCase()}:
                    <span className="text-foreground ml-1 font-semibold">{`${peakValue}${suffix}`}</span>
                  </div>
                  <Badge variant="outline" className="text-[11px]">
                    {metricLabel}
                  </Badge>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export default DensityProfilePanel
