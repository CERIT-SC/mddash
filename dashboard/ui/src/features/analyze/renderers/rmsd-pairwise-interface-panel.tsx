import { useMemo, useState, type FC } from "react"

import { Badge, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@e-infra/design-system"

import type { RMSDPairwiseAnalysis } from "../analysis-types"
import { HeatmapMatrix } from "../charts"
import { downsampleMatrix } from "../charts/utils"

const MAX_INTERFACE_RESOLUTION = 512

const formatFrameLabel = (start: number | undefined, step: number | undefined, index: number) => {
  if (typeof start === "number" && typeof step === "number") {
    return String(start + index * step)
  }
  return String(index)
}

const buildRangeLabel = (
  start: number | undefined,
  step: number | undefined,
  range: { start: number; end: number }
) => {
  if (range.start === range.end) {
    return formatFrameLabel(start, step, range.start)
  }
  return `${formatFrameLabel(start, step, range.start)}-${formatFrameLabel(start, step, range.end)}`
}

const RMSDPairwiseInterfacePanel: FC<{ data: RMSDPairwiseAnalysis }> = ({ data }) => {
  const entries = data?.data ?? []
  const hasEntries = entries.length > 0
  const [activeIndex, setActiveIndex] = useState(0)
  const safeIndex = hasEntries ? Math.min(activeIndex, entries.length - 1) : 0
  const activeEntry = hasEntries ? entries[safeIndex] : undefined

  const heatmapPayload = useMemo(() => {
    if (!hasEntries) {
      return null
    }

    const matrix = activeEntry?.rmsds ?? []
    const {
      matrix: sampledMatrix,
      rowStride,
      colStride,
      rowPositions,
      colPositions,
    } = downsampleMatrix(matrix, MAX_INTERFACE_RESOLUTION)

    if (!sampledMatrix.length || !sampledMatrix[0]?.length) {
      return null
    }

    const triples: Array<[number, number, number]> = []
    for (let row = 0; row < sampledMatrix.length; row += 1) {
      for (let col = 0; col < sampledMatrix[row].length; col += 1) {
        triples.push([col, row, sampledMatrix[row][col] ?? 0])
      }
    }

    const xLabels = colPositions.map((range) => buildRangeLabel(data.start, data.step, range))
    const yLabels = rowPositions.map((range) => buildRangeLabel(data.start, data.step, range))

    return {
      triples,
      xLabels,
      yLabels,
      rowStride,
      colStride,
      rawSize: {
        rows: matrix.length,
        cols: matrix[0]?.length ?? 0,
      },
    }
  }, [activeEntry, data.start, data.step, hasEntries])

  if (!hasEntries) {
    return (
      <div className="text-text-muted flex h-full items-center justify-center text-sm">
        No interface RMSD matrices available.
      </div>
    )
  }

  if (!heatmapPayload) {
    return (
      <div className="text-text-muted flex h-full items-center justify-center text-sm">
        Unable to build interface RMSD heatmap for the selected entry.
      </div>
    )
  }

  const { triples, xLabels, yLabels, rowStride, colStride, rawSize } = heatmapPayload
  const isDownsampled = rowStride > 1 || colStride > 1
  const frameCount = activeEntry?.rmsds?.length ?? 0

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="space-y-1">
        <p className="text-sm font-medium">Interface pairwise RMSD</p>
        <p className="text-text-muted text-xs">
          Compare deviations restricted to interface residues for each interaction. Use the selector to switch between
          interactions and inspect frame windows with the heatmap.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="border-border rounded-md border p-3">
          <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Active interface</p>
          <p className="text-base font-semibold">{activeEntry?.name?.trim() || `Interaction ${safeIndex + 1}`}</p>
        </div>
        <div className="border-border rounded-md border p-3">
          <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Frames captured</p>
          <p className="text-base font-semibold">{frameCount || "N/A"}</p>
        </div>
        <div className="border-border rounded-md border p-3">
          <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Frame step</p>
          <p className="text-base font-semibold">{typeof data.step === "number" ? `${data.step}` : "N/A"}</p>
        </div>
        <div className="border-border rounded-md border p-3">
          <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Matrix resolution</p>
          <p className="text-base font-semibold">
            {rawSize.rows && rawSize.cols ? `${rawSize.rows} × ${rawSize.cols}` : "N/A"}
          </p>
        </div>
      </div>

      <div className="border-border rounded-lg border p-4">
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-sm font-medium">Pairwise deviation heatmap</p>
              <p className="text-text-muted text-xs">
                Darker colors indicate higher RMSD between the selected interface frames.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">
                Raw {rawSize.rows || 0} × {rawSize.cols || 0}
              </Badge>
              {isDownsampled && (
                <Badge variant="secondary">
                  Stride {rowStride} × {colStride}
                </Badge>
              )}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {entries.length > 1 && (
              <Select
                value={String(safeIndex)}
                onValueChange={(value) => {
                  const idx = Number.parseInt(value, 10)
                  if (!Number.isNaN(idx)) {
                    setActiveIndex(idx)
                  }
                }}
              >
                <SelectTrigger className="w-64 text-sm">
                  <SelectValue placeholder="Select interaction" />
                </SelectTrigger>
                <SelectContent>
                  {entries.map((entry, idx) => (
                    <SelectItem key={`${entry.name}-${idx}`} value={String(idx)}>
                      {entry.name?.trim() || `Interaction ${idx + 1}`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {!isDownsampled && <Badge variant="outline">Full resolution</Badge>}
          </div>
          <div className="min-h-[380px]">
            <HeatmapMatrix
              data={triples}
              xLabels={xLabels}
              yLabels={yLabels}
              title={activeEntry?.name ? `Interface · ${activeEntry.name}` : "Interface RMSD"}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

export default RMSDPairwiseInterfacePanel
