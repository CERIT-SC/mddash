import { useEffect, useMemo, useState, type FC } from "react"

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@e-infra/design-system"

import type { HydrogenBondsAnalysis } from "../analysis-types"
import { buildTimeSeries, downsampleMatrix, formatStatValue, HeatmapMatrix, LineChart } from "../charts"

type HydrogenBondEntry = {
  id: string
  label: string
  hbonds: boolean[][]
  donors: number[]
  acceptors: number[]
  hydrogens: number[]
}

const normalizeEntry = (entry: unknown, index: number): HydrogenBondEntry => {
  if (!entry || typeof entry !== "object") {
    return {
      id: `${index}`,
      label: `Interaction ${index + 1}`,
      hbonds: [],
      donors: [],
      acceptors: [],
      hydrogens: [],
    }
  }

  const record = entry as HydrogenBondsAnalysis["data"][number]
  const label =
    typeof record?.name === "string" && record.name.trim().length ? record.name.trim() : `Interaction ${index + 1}`

  const sanitizeBoolMatrix = (matrix: unknown): boolean[][] => {
    if (!Array.isArray(matrix)) return []
    return matrix.map((row) => (Array.isArray(row) ? row.map((value) => value === true) : []))
  }

  const sanitizeNumberArray = (values: unknown): number[] =>
    Array.isArray(values)
      ? values.map((value) => (typeof value === "number" && Number.isFinite(value) ? value : -1))
      : []

  return {
    id: `${index}`,
    label,
    hbonds: sanitizeBoolMatrix(record?.hbonds),
    donors: sanitizeNumberArray(record?.donors),
    acceptors: sanitizeNumberArray(record?.acceptors),
    hydrogens: sanitizeNumberArray(record?.hydrogens),
  }
}

const countSeries = (matrix: boolean[][]): number[] => {
  const frameCount = matrix.reduce((max, row) => Math.max(max, row.length), 0)
  if (!frameCount) return []
  const counts = Array.from({ length: frameCount }, () => 0)
  matrix.forEach((row) => {
    row.forEach((value, frameIndex) => {
      if (value === true) {
        counts[frameIndex] += 1
      }
    })
  })
  return counts
}

const toHeatmapPayload = (matrix: boolean[][]) => {
  if (!matrix.length) {
    return {
      data: [] as Array<[number, number, number]>,
      xLabels: [] as string[],
      yLabels: [] as string[],
    }
  }

  const numericMatrix = matrix.map((row) => row.map((value) => (value ? 1 : 0)))
  const { matrix: reduced, rowPositions, colPositions } = downsampleMatrix(numericMatrix, 400)

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
    xLabels: colPositions.map(({ start, end }) => formatLabel("Frames", start, end)),
    yLabels: rowPositions.map(({ start, end }) => formatLabel("Bond", start, end)),
  }
}

const computeOccupancies = (matrix: boolean[][]): Array<{ index: number; occupancy: number }> => {
  const frameCount = matrix.reduce((max, row) => Math.max(max, row.length), 0)
  if (!frameCount) return []
  return matrix.map((row, index) => {
    const trueCount = row.reduce((sum, value) => sum + (value ? 1 : 0), 0)
    return {
      index,
      occupancy: trueCount / frameCount,
    }
  })
}

const describeBond = (index: number, donors: number[], acceptors: number[], hydrogens: number[]) => {
  const formatIndex = (value: number | undefined) => (typeof value === "number" && value >= 0 ? value : "?")
  const donor = formatIndex(donors[index])
  const acceptor = formatIndex(acceptors[index])
  const hydrogen = formatIndex(hydrogens[index])
  return `D ${donor} -> A ${acceptor} (H ${hydrogen})`
}

const HydrogenBondsAnalysisPanel: FC<{ data: HydrogenBondsAnalysis }> = ({ data }) => {
  const interactions = useMemo<HydrogenBondEntry[]>(() => {
    if (!Array.isArray(data.data)) return []
    return data.data.map((entry, index) => normalizeEntry(entry, index))
  }, [data])

  const [selectedInteractionId, setSelectedInteractionId] = useState<string>(interactions[0]?.id ?? "")

  useEffect(() => {
    if (!interactions.length) return
    if (!interactions.some((entry) => entry.id === selectedInteractionId)) {
      setSelectedInteractionId(interactions[0]?.id ?? "")
    }
  }, [interactions, selectedInteractionId])

  const selectedInteraction = interactions.find((entry) => entry.id === selectedInteractionId)

  const activeMatrix = useMemo(() => selectedInteraction?.hbonds ?? [], [selectedInteraction])
  const frameCount = useMemo(() => activeMatrix.reduce((max, row) => Math.max(max, row.length), 0), [activeMatrix])

  const countsPerFrame = useMemo(() => countSeries(activeMatrix), [activeMatrix])
  const countSeriesData = useMemo(() => {
    if (!countsPerFrame.length) return []
    return [
      {
        name: "Bonds formed",
        data: buildTimeSeries(countsPerFrame, { start: 0, step: 1 }),
      },
    ]
  }, [countsPerFrame])

  const heatmapPayload = useMemo(() => toHeatmapPayload(activeMatrix), [activeMatrix])
  const occupancies = useMemo(() => computeOccupancies(activeMatrix), [activeMatrix])

  const summaryStats = useMemo(() => {
    if (!countsPerFrame.length) return undefined
    const total = countsPerFrame.reduce((sum, value) => sum + value, 0)
    return {
      max: Math.max(...countsPerFrame),
      average: total / countsPerFrame.length,
    }
  }, [countsPerFrame])

  const topBonds = useMemo(
    () =>
      occupancies
        .filter((entry) => Number.isFinite(entry.occupancy))
        .sort((a, b) => b.occupancy - a.occupancy)
        .slice(0, 6),
    [occupancies]
  )

  if (!interactions.length) {
    return (
      <div className="text-text-muted flex h-full items-center justify-center text-sm">
        No hydrogen bond analysis data available.
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-sm font-medium">Hydrogen bond persistence</p>
          <p className="text-text-muted text-xs">Tracks per-interaction H-bond counts and occupancy across frames.</p>
        </div>
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
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="border-border space-y-3 rounded-lg border p-4">
          <div>
            <p className="text-text-muted text-xs tracking-wide uppercase">Interaction</p>
            <p className="text-sm font-semibold">{selectedInteraction?.label ?? "Interaction"}</p>
          </div>
          <div className="text-text-muted space-y-1 text-xs">
            <p>Total bonds: {activeMatrix.length || 0}</p>
            <p>Frames analyzed: {frameCount || 0}</p>
          </div>
          {summaryStats && (
            <div className="text-text-muted space-y-1 text-xs">
              <p>Avg. formed: {formatStatValue(summaryStats.average)}</p>
              <p>Max formed: {summaryStats.max}</p>
            </div>
          )}
          {topBonds.length > 0 && (
            <div>
              <p className="text-text-muted mb-1 text-xs tracking-wide uppercase">Top occupancy bonds</p>
              <ul className="text-text-muted space-y-1 text-xs">
                {topBonds.map((bond) => (
                  <li key={bond.index}>
                    {describeBond(
                      bond.index,
                      selectedInteraction?.donors ?? [],
                      selectedInteraction?.acceptors ?? [],
                      selectedInteraction?.hydrogens ?? []
                    )}
                    :<span className="text-text font-medium">{`${(bond.occupancy * 100).toFixed(1)}%`}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="border-border flex min-h-[280px] flex-col rounded-lg border p-4 xl:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Bonds formed per frame</p>
              <p className="text-text-muted text-xs">Count of hydrogen bonds active at each frame.</p>
            </div>
            <p className="text-text-muted text-xs">Frames: {countsPerFrame.length || 0}</p>
          </div>
          <div className="min-h-[220px] flex-1">
            {countSeriesData.length ? (
              <LineChart series={countSeriesData} xLabel="Frame index" yLabel="Active H-bonds" yScale />
            ) : (
              <div className="text-text-muted flex h-full items-center justify-center text-sm">
                No hydrogen bond time-series data available.
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="border-border flex min-h-[320px] flex-col rounded-lg border p-4">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Bond occupancy heatmap</p>
            <p className="text-text-muted text-xs">
              Rows represent bonds, columns are frame windows. Values are 1 when the bond is formed.
            </p>
          </div>
          <p className="text-text-muted text-xs">Cells: {heatmapPayload.data.length}</p>
        </div>
        <div className="min-h-[280px] flex-1">
          {heatmapPayload.data.length ? (
            <HeatmapMatrix
              data={heatmapPayload.data}
              xLabels={heatmapPayload.xLabels}
              yLabels={heatmapPayload.yLabels}
              title={selectedInteraction?.label}
              enableFilter={false}
            />
          ) : (
            <div className="text-text-muted flex h-full items-center justify-center text-sm">
              No bond occupancy data available.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default HydrogenBondsAnalysisPanel
