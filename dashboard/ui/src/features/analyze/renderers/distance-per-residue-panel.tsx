import { useEffect, useMemo, useState, type FC } from "react"

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@e-infra/design-system"

import type { DistancePerResidueAnalysis } from "../analysis-types"
import { downsampleMatrix, formatStatValue, HeatmapMatrix } from "../charts"

const MATRIX_VIEWS = [
  { value: "means", label: "Mean distances" },
  { value: "stdvs", label: "Std. deviation" },
] as const

type MatrixView = (typeof MATRIX_VIEWS)[number]["value"]

type InteractionMatrix = {
  id: string
  label: string
  means: number[][]
  stdvs: number[][]
}

const sanitizeMatrix = (matrix: unknown): number[][] => {
  if (!Array.isArray(matrix) || !matrix.length) return []
  return matrix.map((row) =>
    Array.isArray(row) ? row.map((value) => (typeof value === "number" && Number.isFinite(value) ? value : 0)) : []
  )
}

const buildHeatmapPayload = (matrix: number[][]) => {
  if (!matrix.length) {
    return {
      data: [] as Array<[number, number, number]>,
      xLabels: [] as string[],
      yLabels: [] as string[],
    }
  }

  const { matrix: reduced, rowPositions, colPositions } = downsampleMatrix(matrix)

  const formatLabel = (prefix: string, start: number, end: number) =>
    start === end ? `${prefix} ${start + 1}` : `${prefix} ${start + 1}-${end + 1}`

  const data: Array<[number, number, number]> = []
  reduced.forEach((row, rowIndex) => {
    row.forEach((value, colIndex) => {
      const safeValue = typeof value === "number" && Number.isFinite(value) ? value : 0
      data.push([colIndex, rowIndex, safeValue])
    })
  })

  return {
    data,
    xLabels: colPositions.map(({ start, end }) => formatLabel("Agent 1", start, end)),
    yLabels: rowPositions.map(({ start, end }) => formatLabel("Agent 2", start, end)),
  }
}

const computeMatrixStats = (matrix: number[][]): { average: number; min: number; max: number } | undefined => {
  if (!matrix.length) return undefined
  let total = 0
  let count = 0
  let min = Number.POSITIVE_INFINITY
  let max = Number.NEGATIVE_INFINITY

  matrix.forEach((row) => {
    row.forEach((value) => {
      if (typeof value === "number" && Number.isFinite(value)) {
        total += value
        count += 1
        if (value < min) min = value
        if (value > max) max = value
      }
    })
  })

  if (!count) return undefined

  return {
    average: total / count,
    min,
    max,
  }
}

const getTopPairs = (matrix: number[][], limit = 6): Array<{ row: number; col: number; value: number }> => {
  const entries: Array<{ row: number; col: number; value: number }> = []
  matrix.forEach((row, rowIndex) => {
    row.forEach((value, colIndex) => {
      if (typeof value === "number" && Number.isFinite(value)) {
        entries.push({ row: rowIndex, col: colIndex, value })
      }
    })
  })
  return entries.sort((a, b) => a.value - b.value).slice(0, limit)
}

const DistancePerResiduePanel: FC<{ data: DistancePerResidueAnalysis }> = ({ data }) => {
  const interactions = useMemo<InteractionMatrix[]>(() => {
    if (!Array.isArray(data.data)) return []
    return data.data.map((entry, index) => {
      const label =
        typeof entry?.name === "string" && entry.name.trim().length ? entry.name.trim() : `Interaction ${index + 1}`
      return {
        id: `${index}`,
        label,
        means: sanitizeMatrix(entry?.means),
        stdvs: sanitizeMatrix(entry?.stdvs),
      }
    })
  }, [data])

  const [selectedInteractionId, setSelectedInteractionId] = useState<string>(interactions[0]?.id ?? "")
  const [view, setView] = useState<MatrixView>("means")

  useEffect(() => {
    if (!interactions.length) return
    if (!interactions.some((entry) => entry.id === selectedInteractionId)) {
      setSelectedInteractionId(interactions[0]?.id ?? "")
    }
  }, [interactions, selectedInteractionId])

  const selectedInteraction = interactions.find((entry) => entry.id === selectedInteractionId)

  const activeMatrix = useMemo(() => {
    if (!selectedInteraction) return []
    return view === "means" ? selectedInteraction.means : selectedInteraction.stdvs
  }, [selectedInteraction, view])

  const heatmapPayload = useMemo(() => buildHeatmapPayload(activeMatrix), [activeMatrix])

  const matrixStats = useMemo(() => computeMatrixStats(activeMatrix), [activeMatrix])

  const topPairs = useMemo(() => getTopPairs(activeMatrix), [activeMatrix])

  const agent2Residues = activeMatrix.length
  const agent1Residues = activeMatrix[0]?.length ?? 0

  if (!interactions.length) {
    return (
      <div className="text-text-muted flex h-full items-center justify-center text-sm">
        No distance-per-residue data available.
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-sm font-medium">Residue distance statistics</p>
          <p className="text-text-muted text-xs">Agent 1 residues on the x-axis, Agent 2 residues on the y-axis.</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {interactions.length > 1 && (
            <div className="flex items-center gap-2">
              <span className="text-text-muted text-xs">Interaction</span>
              <Select value={selectedInteractionId} onValueChange={setSelectedInteractionId}>
                <SelectTrigger className="h-8 w-48 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {interactions.map((entry) => (
                    <SelectItem key={entry.id} value={entry.id}>
                      {entry.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="flex items-center gap-2">
            <span className="text-text-muted text-xs">View</span>
            <Select value={view} onValueChange={(value) => setView(value as MatrixView)}>
              <SelectTrigger className="h-8 w-40 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MATRIX_VIEWS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-4">
        <div className="border-border space-y-3 rounded-lg border p-4">
          <div>
            <p className="text-text-muted text-xs tracking-wide uppercase">Interaction</p>
            <p className="text-sm font-semibold">{selectedInteraction?.label ?? "Interaction"}</p>
          </div>
          <div className="text-text-muted space-y-1 text-xs">
            <p>Agent 1 residues: {agent1Residues || "-"}</p>
            <p>Agent 2 residues: {agent2Residues || "-"}</p>
          </div>
          {matrixStats && (
            <div className="text-text-muted space-y-1 text-xs">
              <p>
                Avg: <span className="text-text font-medium">{formatStatValue(matrixStats.average)}</span>
              </p>
              <p>
                Min: <span className="text-text font-medium">{formatStatValue(matrixStats.min)}</span>
              </p>
              <p>
                Max: <span className="text-text font-medium">{formatStatValue(matrixStats.max)}</span>
              </p>
            </div>
          )}
          {topPairs.length > 0 && (
            <div>
              <p className="text-text-muted mb-1 text-xs tracking-wide uppercase">Closest residue pairs</p>
              <ul className="text-text-muted space-y-1 text-xs">
                {topPairs.map((pair, index) => (
                  <li key={`${pair.row}-${pair.col}`}>
                    #{index + 1} · A1 {pair.col + 1} ↔ A2 {pair.row + 1}:{" "}
                    <span className="text-text font-medium">{formatStatValue(pair.value)} A</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="border-border flex min-h-80 flex-col rounded-lg border p-4 xl:col-span-3">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">{view === "means" ? "Mean distances" : "Distance variability"}</p>
              <p className="text-text-muted text-xs">
                Values are grouped when matrices exceed 256×256 to keep rendering smooth.
              </p>
            </div>
            <p className="text-text-muted text-xs">Cells: {heatmapPayload.data.length}</p>
          </div>
          <div className="min-h-70 flex-1">
            {heatmapPayload.data.length ? (
              <HeatmapMatrix
                data={heatmapPayload.data}
                xLabels={heatmapPayload.xLabels}
                yLabels={heatmapPayload.yLabels}
                title={selectedInteraction?.label}
              />
            ) : (
              <div className="text-text-muted flex h-full items-center justify-center text-sm">
                No matrix data available for this interaction.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default DistancePerResiduePanel
