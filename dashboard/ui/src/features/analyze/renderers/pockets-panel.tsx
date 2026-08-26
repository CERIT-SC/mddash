import { useEffect, useMemo, useState, type FC } from "react"

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@e-infra/design-system"

import type { PocketsAnalysis } from "../analysis-types"
import { BarChart, buildTimeSeries, formatStatValue, LineChart } from "../charts"

const MAX_BAR_POCKETS = 15

type PocketEntry = {
  id: string
  label: string
  volumes: number[]
  atomCount: number
}

const sanitizeName = (name: unknown, index: number): string => {
  if (typeof name === "string" && name.trim().length > 0) {
    return name.trim()
  }
  return `Pocket ${index + 1}`
}

const computeBasicStats = (
  values: number[]
):
  | {
      average: number
      min: number
      max: number
    }
  | undefined => {
  const numericValues = values.filter((value) => Number.isFinite(value))
  if (!numericValues.length) {
    return undefined
  }

  const total = numericValues.reduce((sum, value) => sum + value, 0)
  return {
    average: total / numericValues.length,
    min: Math.min(...numericValues),
    max: Math.max(...numericValues),
  }
}

const PocketsAnalysisPanel: FC<{ data: PocketsAnalysis }> = ({ data }) => {
  const pockets = useMemo<PocketEntry[]>(() => {
    const rawEntries = Array.isArray(data.data) ? data.data : []
    return rawEntries.map((entry, index) => {
      const label = sanitizeName(entry?.name, index)
      const volumes = Array.isArray(entry?.volumes)
        ? entry.volumes.map((value) => (typeof value === "number" && Number.isFinite(value) ? value : NaN))
        : []
      const atomCount = Array.isArray(entry?.atoms) ? entry.atoms.length : 0
      return {
        id: `${index}-${label}`,
        label,
        volumes,
        atomCount,
      }
    })
  }, [data])

  const [selectedPocket, setSelectedPocket] = useState<string>("")

  useEffect(() => {
    if (!pockets.length) return
    const fallback = pockets[0]?.id ?? ""
    if (!selectedPocket || !pockets.some((pocket) => pocket.id === selectedPocket)) {
      setSelectedPocket(fallback)
    }
  }, [pockets, selectedPocket])

  const activePocket = pockets.find((pocket) => pocket.id === selectedPocket)

  const pocketSeries = useMemo(
    () =>
      activePocket
        ? [
            {
              name: `${activePocket.label} volume`,
              data: buildTimeSeries(activePocket.volumes, {
                start: 0,
                step: 1,
              }),
            },
          ]
        : [],
    [activePocket]
  )

  const pocketStats = useMemo(
    () => (activePocket ? computeBasicStats(activePocket.volumes) : undefined),
    [activePocket]
  )

  const topPocketAverages = useMemo(() => {
    return pockets
      .map((pocket) => {
        const stats = computeBasicStats(pocket.volumes)
        return stats
          ? {
              label: pocket.label,
              average: stats.average,
            }
          : undefined
      })
      .filter((entry): entry is { label: string; average: number } => Boolean(entry))
      .sort((a, b) => b.average - a.average)
      .slice(0, MAX_BAR_POCKETS)
  }, [pockets])

  const barCategories = topPocketAverages.map((entry) => entry.label)
  const barSeries = [
    {
      name: "Avg volume",
      data: topPocketAverages.map((entry) => entry.average),
    },
  ]

  return pockets.length ? (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="border-border flex min-h-[280px] flex-col rounded-lg border p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium">Pocket volume over time</p>
              <p className="text-text-muted text-xs">Frame-wise pocket volume (A^3)</p>
            </div>
            {pockets.length > 1 && (
              <div className="flex items-center gap-2">
                <span className="text-text-muted text-xs">Pocket</span>
                <Select value={selectedPocket} onValueChange={setSelectedPocket}>
                  <SelectTrigger className="h-8 w-48 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {pockets.map((pocket) => (
                      <SelectItem key={pocket.id} value={pocket.id}>
                        {pocket.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          {pocketStats && (
            <div className="text-text-muted mb-2 flex flex-wrap gap-x-6 gap-y-1 text-xs">
              <span>Avg: {formatStatValue(pocketStats.average)}</span>
              <span>Min: {formatStatValue(pocketStats.min)}</span>
              <span>Max: {formatStatValue(pocketStats.max)}</span>
              {typeof activePocket?.atomCount === "number" && <span>Atoms: {activePocket.atomCount}</span>}
            </div>
          )}

          <div className="min-h-[220px] flex-1">
            {pocketSeries.length ? (
              <LineChart
                series={pocketSeries}
                xLabel="Frame index"
                yLabel="Pocket volume (A^3)"
                showLegend={false}
                yScale
              />
            ) : (
              <div className="text-text-muted flex h-full items-center justify-center text-sm">
                No pocket time-series data available.
              </div>
            )}
          </div>
        </div>

        <div className="border-border flex min-h-[280px] flex-col rounded-lg border p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Average pocket volumes</p>
              <p className="text-text-muted text-xs">Top {barCategories.length} pockets by average volume</p>
            </div>
            <p className="text-text-muted text-xs">Total pockets: {pockets.length}</p>
          </div>
          <div className="min-h-[220px] flex-1">
            {barCategories.length ? (
              <BarChart categories={barCategories} series={barSeries} horizontal showLegend={false} />
            ) : (
              <div className="text-text-muted flex h-full items-center justify-center text-sm">
                Not enough pocket data for bar chart.
              </div>
            )}
          </div>
          {pockets.length > MAX_BAR_POCKETS && (
            <p className="text-text-muted mt-2 text-[11px]">
              Showing top {MAX_BAR_POCKETS} pockets. Filter in 3D to inspect all pockets.
            </p>
          )}
        </div>
      </div>
    </div>
  ) : (
    <div className="text-text-muted flex h-full items-center justify-center text-sm">
      No pocket analysis data available.
    </div>
  )
}

export default PocketsAnalysisPanel
