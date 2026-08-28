import { useState, type FC } from "react"

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@e-infra/design-system"

import type { RMSDPairwiseAnalysis } from "../analysis-types"
import { HeatmapMatrix } from "../charts"
import { downsampleMatrix } from "../charts/utils"

type RMSDPairwiseHeatmapProps = {
  data: RMSDPairwiseAnalysis
}

const MAX_HEATMAP_RESOLUTION = 512

const RMSDPairwiseHeatmap: FC<RMSDPairwiseHeatmapProps> = ({ data }) => {
  const entries = data.data ?? []
  const [activeIndex, setActiveIndex] = useState(0)

  if (entries.length === 0) return null

  const clampedIndex = Math.min(activeIndex, entries.length - 1)
  const activeEntry = entries[clampedIndex]
  const matrix: number[][] = activeEntry?.rmsds ?? []
  const {
    matrix: sampledMatrix,
    rowStride,
    colStride,
    rowPositions,
    colPositions,
  } = downsampleMatrix(matrix, MAX_HEATMAP_RESOLUTION)
  const triples: Array<[number, number, number]> = []
  for (let i = 0; i < sampledMatrix.length; i++) {
    for (let j = 0; j < sampledMatrix[i].length; j++) {
      triples.push([j, i, sampledMatrix[i][j] ?? 0])
    }
  }
  const rowCount = sampledMatrix.length
  const colCount = sampledMatrix[0]?.length ?? 0
  const start = data.start
  const step = data.step

  const formatFrameLabel = (index: number) =>
    start !== null && start !== undefined && step !== null && step !== undefined
      ? String(start + index * step)
      : String(index)

  const buildRangeLabel = ({ start: originStart, end: originEnd }: { start: number; end: number }) => {
    if (originStart === originEnd) {
      return formatFrameLabel(originStart)
    }
    return `${formatFrameLabel(originStart)}-${formatFrameLabel(originEnd)}`
  }

  const yLabels = rowPositions.map(buildRangeLabel)
  const xLabels = colPositions.map(buildRangeLabel)

  if (rowCount === 0 || colCount === 0) return null

  const isDownsampled = rowStride > 1 || colStride > 1

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {entries.length > 1 && (
          <Select
            value={String(clampedIndex)}
            onValueChange={(value) => {
              const nextIndex = Number.parseInt(value, 10)
              if (!Number.isNaN(nextIndex)) {
                setActiveIndex(nextIndex)
              }
            }}
          >
            <SelectTrigger className="w-56">
              <SelectValue placeholder="Select interaction" />
            </SelectTrigger>
            <SelectContent>
              {entries.map((entry, idx) => (
                <SelectItem key={`${entry.name}-${idx}`} value={String(idx)}>
                  {entry.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {isDownsampled && (
          <span className="text-text-muted text-xs">
            Showing downsampled matrix (stride {rowStride} × {colStride})
          </span>
        )}
      </div>
      <div className="min-h-0 flex-1">
        <HeatmapMatrix
          data={triples}
          xLabels={xLabels}
          yLabels={yLabels}
          title={`RMSD pairwise${activeEntry?.name ? ` · ${activeEntry.name}` : ""}`}
        />
      </div>
    </div>
  )
}

export default RMSDPairwiseHeatmap
