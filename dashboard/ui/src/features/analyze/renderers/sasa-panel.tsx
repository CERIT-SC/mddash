import { useEffect, useMemo, useState, type FC } from "react"

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@e-infra/design-system"

import type { SolventAccessibleSurfaceAnalysis } from "../analysis-types"
import { BarChart, buildTimeSeries, formatStatValue, LineChart } from "../charts"

const MAX_BAR_RESIDUES = 25

type ResidueSeries = {
  id: string
  label: string
  values: Array<number | null>
}

type ResidueAverage = {
  label: string
  average: number
}

const toNumericArray = (values: unknown[]): Array<number | null> =>
  values.map((value) => (typeof value === "number" && Number.isFinite(value) ? value : null))

const computeAverage = (values: Array<number | null>): number | undefined => {
  let count = 0
  let sum = 0
  values.forEach((value) => {
    if (typeof value === "number" && Number.isFinite(value)) {
      count += 1
      sum += value
    }
  })
  return count ? sum / count : undefined
}

const computeStats = (
  values: number[]
):
  | {
      average: number
      min: number
      max: number
    }
  | undefined => {
  const numeric = values.filter((value) => Number.isFinite(value))
  if (!numeric.length) return undefined
  const total = numeric.reduce((sum, value) => sum + value, 0)
  return {
    average: total / numeric.length,
    min: Math.min(...numeric),
    max: Math.max(...numeric),
  }
}

const normalizeResidues = (data: SolventAccessibleSurfaceAnalysis): ResidueSeries[] => {
  if (!Array.isArray(data.saspf) || !data.saspf.length) {
    return []
  }

  return data.saspf.map((row, index) => ({
    id: `res-${index}`,
    label: `Residue ${index + 1}`,
    values: Array.isArray(row) ? toNumericArray(row) : [],
  }))
}

const SasaAnalysisPanel: FC<{ data: SolventAccessibleSurfaceAnalysis }> = ({ data }) => {
  const residues = useMemo(() => normalizeResidues(data), [data])
  const [selectedResidueId, setSelectedResidueId] = useState<string>("")

  useEffect(() => {
    if (!residues.length) return
    const fallback = residues[0]?.id ?? ""
    if (!selectedResidueId || !residues.some((residue) => residue.id === selectedResidueId)) {
      setSelectedResidueId(fallback)
    }
  }, [residues, selectedResidueId])

  const selectedResidue = residues.find((residue) => residue.id === selectedResidueId)

  const frameStep = Number.isFinite(data.step) && data.step ? data.step : 1

  const totalSeriesValues = useMemo(() => {
    const frameCount = Math.max(...residues.map((entry) => entry.values.length), 0)
    return Array.from({ length: frameCount }, (_, frameIndex) => {
      let sum = 0
      residues.forEach((entry) => {
        const value = entry.values[frameIndex]
        if (typeof value === "number" && Number.isFinite(value)) {
          sum += value
        }
      })
      return sum
    })
  }, [residues])

  const totalSeries = useMemo(
    () =>
      totalSeriesValues.length
        ? buildTimeSeries(totalSeriesValues, {
            start: 0,
            step: frameStep,
          })
        : [],
    [totalSeriesValues, frameStep]
  )

  const residueOverlaySeries = useMemo(() => {
    if (!selectedResidue) return []
    const values = selectedResidue.values.map((value) =>
      typeof value === "number" && Number.isFinite(value) ? value : NaN
    )
    return buildTimeSeries(values, { start: 0, step: frameStep })
  }, [selectedResidue, frameStep])

  const totalStats = useMemo(() => computeStats(totalSeriesValues), [totalSeriesValues])

  const residueStats = useMemo(
    () => (selectedResidue ? computeAverage(selectedResidue.values) : undefined),
    [selectedResidue]
  )

  const residueAverages = useMemo<ResidueAverage[]>(() => {
    return residues
      .map((entry) => {
        const avg = computeAverage(entry.values)
        return typeof avg === "number"
          ? {
              label: entry.label,
              average: avg,
            }
          : undefined
      })
      .filter((entry): entry is ResidueAverage => Boolean(entry))
      .sort((a, b) => b.average - a.average)
      .slice(0, MAX_BAR_RESIDUES)
  }, [residues])

  const barCategories = residueAverages.map((entry) => entry.label)
  const barSeries = [
    {
      name: "Avg SASA",
      data: residueAverages.map((entry) => entry.average),
    },
  ]

  if (!residues.length) {
    return (
      <div className="text-text-muted flex h-full items-center justify-center text-sm">
        No SASA analysis data available.
      </div>
    )
  }

  const lineSeries = [
    {
      name: "Total SASA",
      data: totalSeries,
    },
  ]

  if (residueOverlaySeries.length) {
    lineSeries.push({
      name: selectedResidue?.label ?? "Residue",
      data: residueOverlaySeries,
    })
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="border-border flex min-h-70 flex-col rounded-lg border p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium">SASA over time</p>
              <p className="text-text-muted text-xs">
                Total solvent accessible surface area and optional residue overlay
              </p>
            </div>
            {residues.length > 1 && (
              <div className="flex items-center gap-2">
                <span className="text-text-muted text-xs">Residue</span>
                <Select value={selectedResidueId} onValueChange={setSelectedResidueId}>
                  <SelectTrigger className="h-8 w-48 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {residues.map((entry) => (
                      <SelectItem key={entry.id} value={entry.id}>
                        {entry.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          <div className="text-text-muted mb-2 flex flex-wrap gap-x-6 gap-y-1 text-xs">
            {totalStats && (
              <span>
                Total Avg: {formatStatValue(totalStats.average)} (Min: {formatStatValue(totalStats.min)} · Max:{" "}
                {formatStatValue(totalStats.max)})
              </span>
            )}
            {typeof residueStats === "number" && selectedResidue && (
              <span>
                {selectedResidue.label} Avg: {formatStatValue(residueStats)}
              </span>
            )}
          </div>

          <div className="min-h-55 flex-1">
            {lineSeries[0]?.data.length ? (
              <LineChart
                series={lineSeries}
                xLabel={frameStep !== 1 ? `Frame (step ${frameStep})` : "Frame index"}
                yLabel="SASA (A^2)"
                yScale
              />
            ) : (
              <div className="text-text-muted flex h-full items-center justify-center text-sm">
                No SASA time-series data available.
              </div>
            )}
          </div>
        </div>

        <div className="border-border flex min-h-70 flex-col rounded-lg border p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Residue exposure ranking</p>
              <p className="text-text-muted text-xs">Average SASA per residue (top {barCategories.length})</p>
            </div>
            <p className="text-text-muted text-xs">Residues analyzed: {residues.length}</p>
          </div>
          <div className="min-h-55 flex-1">
            {barCategories.length ? (
              <BarChart categories={barCategories} series={barSeries} horizontal showLegend={false} />
            ) : (
              <div className="text-text-muted flex h-full items-center justify-center text-sm">
                Not enough residue data for bar chart.
              </div>
            )}
          </div>
          {residues.length > MAX_BAR_RESIDUES && (
            <p className="text-text-muted mt-2 text-[11px]">
              Showing top {MAX_BAR_RESIDUES} residues by exposure. Use the dropdown to inspect others.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

export default SasaAnalysisPanel
