import { useMemo, type FC } from "react"

import type { AreaPerLipidAnalysis } from "../analysis-types"
import { HeatmapMatrix, LineChart } from "../charts"
import type { LineSeries } from "../charts/line-chart"
import { sanitizeNumericArray } from "./utils"

const toNumericMatrix = (matrix: unknown): number[][] => {
  if (!Array.isArray(matrix)) return []
  const sanitized: number[][] = []
  matrix.forEach((row) => {
    if (!Array.isArray(row)) return
    const sanitizedRow = row.map((value) => (typeof value === "number" && Number.isFinite(value) ? value : 0))
    sanitized.push(sanitizedRow)
  })
  return sanitized
}

const buildHeatmapTriples = (matrix: number[][]): Array<[number, number, number]> => {
  const triples: Array<[number, number, number]> = []
  matrix.forEach((row, yIndex) => {
    row.forEach((value, xIndex) => {
      triples.push([xIndex, yIndex, value])
    })
  })
  return triples
}

const buildAxisLabels = (values: unknown, fallbackLength: number, prefix: string): string[] => {
  if (Array.isArray(values) && values.length) {
    return values.map((value, index) => {
      if (typeof value === "number" && Number.isFinite(value)) {
        return value.toFixed(1)
      }
      if (typeof value === "string" && value.trim().length) {
        return value.trim()
      }
      return `${prefix} ${index + 1}`
    })
  }
  return Array.from({ length: fallbackLength }, (_, index) => `${prefix} ${index + 1}`)
}

const formatStat = (value?: number): string => {
  if (typeof value !== "number" || !Number.isFinite(value)) return "N/A"
  return value.toFixed(2)
}

const buildLineSeries = (label: string, values: number[]): LineSeries | undefined => {
  if (!values.length) return undefined
  const data: Array<[number, number]> = values.map((value, index) => [index + 1, value])
  return data.length ? { name: label, data } : undefined
}

const average = (values: number[]): number | undefined => {
  if (!values.length) return undefined
  const total = values.reduce((sum, value) => sum + value, 0)
  return total / values.length
}

const AreaPerLipidPanel: FC<{ data: AreaPerLipidAnalysis }> = ({ data }) => {
  const areaData = data?.data
  const upperMatrix = useMemo(() => toNumericMatrix(areaData?.["upper leaflet"]), [areaData])
  const lowerMatrix = useMemo(() => toNumericMatrix(areaData?.["lower leaflet"]), [areaData])

  const hasAnyMatrix = upperMatrix.length || lowerMatrix.length

  const gridXLabels = useMemo(() => {
    const fallbackLength = upperMatrix[0]?.length ?? lowerMatrix[0]?.length ?? 0
    return buildAxisLabels(areaData?.grid_x, fallbackLength, "X")
  }, [areaData?.grid_x, lowerMatrix, upperMatrix])

  const upperYLabels = useMemo(
    () => buildAxisLabels(areaData?.grid_y, upperMatrix.length, "Y"),
    [areaData?.grid_y, upperMatrix]
  )

  const lowerYLabels = useMemo(
    () => buildAxisLabels(areaData?.grid_y, lowerMatrix.length, "Y"),
    [areaData?.grid_y, lowerMatrix]
  )

  const upperHeatmap = useMemo(() => buildHeatmapTriples(upperMatrix), [upperMatrix])
  const lowerHeatmap = useMemo(() => buildHeatmapTriples(lowerMatrix), [lowerMatrix])

  const sharedRange = useMemo(() => {
    const combined = [...upperMatrix.flat(), ...lowerMatrix.flat()].filter(
      (value) => typeof value === "number" && Number.isFinite(value)
    )
    if (!combined.length) return undefined
    return {
      min: Math.min(...combined),
      max: Math.max(...combined),
    }
  }, [lowerMatrix, upperMatrix])

  const medianArray = useMemo(() => sanitizeNumericArray(areaData?.median), [areaData?.median])
  const stdArray = useMemo(() => sanitizeNumericArray(areaData?.std), [areaData?.std])

  const medianSeries = useMemo(() => {
    const series: LineSeries[] = []
    const medianLine = buildLineSeries("Median", medianArray)
    if (medianLine) {
      series.push(medianLine)
    }
    if (medianArray.length && stdArray.length && medianArray.length === stdArray.length) {
      const plusSeries = buildLineSeries(
        "Median + Std",
        medianArray.map((value, index) => value + stdArray[index])
      )
      const minusSeries = buildLineSeries(
        "Median - Std",
        medianArray.map((value, index) => value - stdArray[index])
      )
      if (plusSeries) series.push(plusSeries)
      if (minusSeries) series.push(minusSeries)
    }
    return series
  }, [medianArray, stdArray])

  const medianSummary = useMemo(() => {
    if (typeof areaData?.median === "number" && Number.isFinite(areaData.median)) {
      return areaData.median
    }
    return average(medianArray)
  }, [areaData?.median, medianArray])

  const stdSummary = useMemo(() => {
    if (typeof areaData?.std === "number" && Number.isFinite(areaData.std)) {
      return areaData.std
    }
    return average(stdArray)
  }, [areaData?.std, stdArray])

  const gridResolution = `${gridXLabels.length || "?"} × ${upperYLabels.length || lowerYLabels.length || "?"}`

  if (!hasAnyMatrix) {
    return (
      <div className="text-text-muted flex h-full items-center justify-center text-sm">
        No area-per-lipid analysis data available.
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="border-border rounded-md border p-3">
          <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Median area</p>
          <p className="text-lg font-semibold">{formatStat(medianSummary)} Å²</p>
        </div>
        <div className="border-border rounded-md border p-3">
          <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Std. deviation</p>
          <p className="text-lg font-semibold">{formatStat(stdSummary)} Å²</p>
        </div>
        <div className="border-border rounded-md border p-3">
          <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Grid resolution</p>
          <p className="text-lg font-semibold">{gridResolution}</p>
        </div>
      </div>

      {medianSeries.length ? (
        <div className="border-border h-64 rounded-lg border p-4">
          <p className="mb-2 text-sm font-medium">Median ± Std over frames</p>
          <LineChart series={medianSeries} xLabel="Frame" yLabel="Å²" showLegend yScale />
        </div>
      ) : null}

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-2">
        <div className="border-border flex min-h-80 flex-col gap-3 rounded-lg border p-4">
          <div>
            <p className="text-sm font-medium">Upper leaflet grid</p>
            <p className="text-text-muted text-xs">Per-cell area contributions for the upper leaflet</p>
          </div>
          <div className="min-h-70 flex-1">
            {upperHeatmap.length ? (
              <HeatmapMatrix
                data={upperHeatmap}
                xLabels={gridXLabels}
                yLabels={upperYLabels}
                enableFilter
                valueRange={sharedRange}
              />
            ) : (
              <div className="text-text-muted flex h-full items-center justify-center text-sm">
                No upper leaflet grid data provided.
              </div>
            )}
          </div>
        </div>
        <div className="border-border flex min-h-80 flex-col gap-3 rounded-lg border p-4">
          <div>
            <p className="text-sm font-medium">Lower leaflet grid</p>
            <p className="text-text-muted text-xs">Mirrored area map for the lower leaflet</p>
          </div>
          <div className="min-h-70 flex-1">
            {lowerHeatmap.length ? (
              <HeatmapMatrix
                data={lowerHeatmap}
                xLabels={gridXLabels}
                yLabels={lowerYLabels}
                enableFilter
                valueRange={sharedRange}
              />
            ) : (
              <div className="text-text-muted flex h-full items-center justify-center text-sm">
                No lower leaflet grid data provided.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default AreaPerLipidPanel
