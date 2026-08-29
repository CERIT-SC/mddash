import { useMemo, type FC } from "react"

import type { ThicknessAnalysis } from "../analysis-types"
import { LineChart } from "../charts"
import type { LineSeries } from "../charts/line-chart"
import { buildLineSeries, sanitizeNumericArray } from "./utils"

const computeStats = (values: number[]) => {
  if (!values.length) return undefined
  const filtered = values.filter((value) => Number.isFinite(value))
  if (!filtered.length) return undefined
  const sum = filtered.reduce((acc, value) => acc + value, 0)
  return {
    average: sum / filtered.length,
    min: Math.min(...filtered),
    max: Math.max(...filtered),
  }
}

const average = (values: number[]) => {
  if (!values.length) return undefined
  const filtered = values.filter((value) => Number.isFinite(value))
  if (!filtered.length) return undefined
  const sum = filtered.reduce((acc, value) => acc + value, 0)
  return sum / filtered.length
}

const formatStat = (value?: number, precision = 2) =>
  typeof value === "number" && Number.isFinite(value) ? value.toFixed(precision) : "N/A"

const ThicknessAnalysisPanel: FC<{ data: ThicknessAnalysis }> = ({ data }) => {
  const dataset = data?.data
  const rawFrames = useMemo(() => (Array.isArray(dataset?.frame) ? dataset.frame : []), [dataset?.frame])
  const thicknessValues = useMemo(() => sanitizeNumericArray(dataset?.thickness), [dataset?.thickness])

  const fallbackLength = thicknessValues.length
  const frameStep = typeof data?.step === "number" && Number.isFinite(data.step) && data.step ? data.step : 1

  const frames = useMemo(() => {
    if (rawFrames.length) {
      return rawFrames.map((value, index) =>
        typeof value === "number" && Number.isFinite(value) ? value : index * frameStep
      )
    }
    return Array.from({ length: fallbackLength }, (_, index) => index * frameStep)
  }, [fallbackLength, frameStep, rawFrames])

  const meanPositive = useMemo(() => sanitizeNumericArray(dataset?.mean_positive), [dataset?.mean_positive])
  const meanNegative = useMemo(() => sanitizeNumericArray(dataset?.mean_negative), [dataset?.mean_negative])
  const stdThickness = useMemo(() => sanitizeNumericArray(dataset?.std_thickness), [dataset?.std_thickness])
  const stdPositive = useMemo(() => sanitizeNumericArray(dataset?.std_positive), [dataset?.std_positive])
  const stdNegative = useMemo(() => sanitizeNumericArray(dataset?.std_negative), [dataset?.std_negative])
  const midplaneValues = useMemo(() => sanitizeNumericArray(dataset?.midplane_z), [dataset?.midplane_z])

  const thicknessSeries = useMemo(
    () => buildLineSeries("Thickness", frames, thicknessValues),
    [frames, thicknessValues]
  )
  const positiveSeries = useMemo(() => buildLineSeries("Mean positive", frames, meanPositive), [frames, meanPositive])
  const negativeSeries = useMemo(() => buildLineSeries("Mean negative", frames, meanNegative), [frames, meanNegative])

  const mainSeries = useMemo(() => {
    const collection: LineSeries[] = []
    if (thicknessSeries) collection.push(thicknessSeries)
    if (positiveSeries) collection.push(positiveSeries)
    if (negativeSeries) collection.push(negativeSeries)
    return collection
  }, [negativeSeries, positiveSeries, thicknessSeries])

  const midplaneSeries = useMemo(() => buildLineSeries("Midplane Z", frames, midplaneValues), [frames, midplaneValues])

  const stats = useMemo(() => computeStats(thicknessValues), [thicknessValues])
  const avgStd = useMemo(() => average(stdThickness), [stdThickness])
  const avgLeafletGap = useMemo(() => {
    if (!meanPositive.length || !meanNegative.length) return undefined
    const limit = Math.min(meanPositive.length, meanNegative.length)
    if (!limit) return undefined
    let sum = 0
    let count = 0
    for (let i = 0; i < limit; i += 1) {
      const pos = meanPositive[i]
      const neg = meanNegative[i]
      if (Number.isFinite(pos) && Number.isFinite(neg)) {
        sum += pos - neg
        count += 1
      }
    }
    return count ? sum / count : undefined
  }, [meanNegative, meanPositive])

  const infoCards = [
    {
      label: "Average thickness",
      value: `${formatStat(stats?.average)} Å`,
    },
    {
      label: "Thickness range",
      value:
        stats && typeof stats.min === "number" && typeof stats.max === "number"
          ? `${stats.min.toFixed(2)}–${stats.max.toFixed(2)} Å`
          : "N/A",
    },
    {
      label: "Avg thickness σ",
      value: `${formatStat(avgStd)} Å`,
    },
    {
      label: "Frames analyzed",
      value: frames.length ? frames.length.toString() : "N/A",
    },
  ]

  if (!mainSeries.length) {
    return (
      <div className="text-text-muted flex h-full items-center justify-center text-sm">
        No membrane thickness analysis data available.
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {infoCards.map((card) => (
          <div key={card.label} className="border-border rounded-md border p-3">
            <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">{card.label}</p>
            <p className="text-lg font-semibold">{card.value}</p>
          </div>
        ))}
      </div>

      <div className="border-border flex min-h-[340px] flex-col gap-3 rounded-lg border p-4">
        <div>
          <p className="text-sm font-medium">Leaflet separation over time</p>
          <p className="text-text-muted text-xs">Overall thickness with positive/negative leaflet centroids</p>
        </div>
        <div className="min-h-[260px] flex-1">
          <LineChart series={mainSeries} xLabel="Frame" yLabel="Å" showLegend yScale />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="border-border flex min-h-[240px] flex-col gap-3 rounded-lg border p-4">
          <div>
            <p className="text-sm font-medium">Midplane drift</p>
            <p className="text-text-muted text-xs">Z-position of the bilayer midplane per frame</p>
          </div>
          <div className="min-h-[180px] flex-1">
            {midplaneSeries ? (
              <LineChart series={[midplaneSeries]} xLabel="Frame" yLabel="Z (Å)" showLegend={false} yScale />
            ) : (
              <div className="text-text-muted flex h-full items-center justify-center text-sm">
                No midplane data provided.
              </div>
            )}
          </div>
        </div>
        <div className="border-border space-y-3 rounded-lg border p-4">
          <div>
            <p className="text-sm font-medium">Stability snapshot</p>
            <p className="text-text-muted text-xs">
              Average standard deviations for each leaflet and the combined thickness
            </p>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-text-muted">Leaflet gap (avg)</span>
              <span className="font-medium">{`${formatStat(avgLeafletGap)} Å`}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-text-muted">σ (positive leaflet)</span>
              <span className="font-medium">{`${formatStat(average(stdPositive))} Å`}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-text-muted">σ (negative leaflet)</span>
              <span className="font-medium">{`${formatStat(average(stdNegative))} Å`}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ThicknessAnalysisPanel
