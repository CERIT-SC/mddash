import type { StatisticalData } from "@/util/analysis-types"

export type XYPoint = [number, number]

interface TimeSeriesOptions {
  start?: number
  step?: number
}

interface DownsampleOptions extends TimeSeriesOptions {
  targetPoints?: number
}

interface StatSeriesOptions extends DownsampleOptions {
  name: string
}

export interface StatSeriesResult {
  name: string
  data: XYPoint[]
  stats: Omit<StatisticalData, "data">
}

const DEFAULT_TARGET_POINTS = 1200
const DEFAULT_HEATMAP_TARGET = 256

export interface DownsampledMatrix {
  matrix: number[][]
  rowStride: number
  colStride: number
  rowPositions: Array<{ start: number; end: number }>
  colPositions: Array<{ start: number; end: number }>
}

function getStride(length: number, targetPoints: number): number {
  if (length <= targetPoints) return 1
  return Math.ceil(length / targetPoints)
}

function normalizeTimeSeriesParams(options: TimeSeriesOptions = {}): Required<TimeSeriesOptions> {
  const { start = 0, step = 1 } = options
  const safeStart = Number.isFinite(start) ? start : 0
  const safeStep = Number.isFinite(step) && step !== 0 ? step : 1
  return { start: safeStart, step: safeStep }
}

export function buildTimeSeries(values: number[], options: TimeSeriesOptions = {}): XYPoint[] {
  const { start, step } = normalizeTimeSeriesParams(options)
  return values.map((y, i) => [start + i * step, y])
}

export function downsampleSeries(values: number[], options: DownsampleOptions = {}): XYPoint[] {
  const targetPoints = options.targetPoints ?? DEFAULT_TARGET_POINTS
  const { start, step } = normalizeTimeSeriesParams(options)

  if (values.length <= targetPoints) {
    return buildTimeSeries(values, { start, step })
  }

  const stride = getStride(values.length, targetPoints)
  const data: XYPoint[] = []
  for (let i = 0; i < values.length; i += stride) {
    data.push([start + i * step, values[i]])
  }
  return data
}

export function downsampleMatrix(matrix: number[][], targetSize: number = DEFAULT_HEATMAP_TARGET): DownsampledMatrix {
  if (matrix.length === 0) {
    return {
      matrix,
      rowStride: 1,
      colStride: 1,
      rowPositions: [],
      colPositions: [],
    }
  }

  const rows = matrix.length
  const cols = matrix[0]?.length ?? 0
  const rowStride = getStride(rows, targetSize)
  const colStride = getStride(cols, targetSize)

  const rowPositions: Array<{ start: number; end: number }> = []
  for (let i = 0; i < rows; i += rowStride) {
    rowPositions.push({
      start: i,
      end: Math.min(i + rowStride, rows) - 1,
    })
  }

  const colPositions: Array<{ start: number; end: number }> = []
  for (let j = 0; j < cols; j += colStride) {
    colPositions.push({
      start: j,
      end: Math.min(j + colStride, cols) - 1,
    })
  }

  if (rowStride === 1 && colStride === 1) {
    return { matrix, rowStride, colStride, rowPositions, colPositions }
  }

  const result: number[][] = []
  for (const { start: rowStart, end: rowEnd } of rowPositions) {
    const newRow: number[] = []
    for (const { start: colStart, end: colEnd } of colPositions) {
      let sum = 0
      let count = 0
      for (let r = rowStart; r <= rowEnd; r++) {
        const sourceRow = matrix[r] ?? []
        for (let c = colStart; c <= colEnd; c++) {
          const value = sourceRow[c]
          if (typeof value === "number" && Number.isFinite(value)) {
            sum += value
            count++
          }
        }
      }
      newRow.push(count > 0 ? sum / count : 0)
    }
    result.push(newRow)
  }

  return { matrix: result, rowStride, colStride, rowPositions, colPositions }
}

export function statToSeries(
  stat: StatisticalData | undefined,
  { name, start = 0, step = 1, targetPoints }: StatSeriesOptions
): StatSeriesResult | undefined {
  if (!stat) return undefined

  const data = targetPoints
    ? downsampleSeries(stat.data, { start, step, targetPoints })
    : buildTimeSeries(stat.data, { start, step })

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { data: _, ...stats } = stat

  return {
    name,
    data,
    stats,
  }
}

export function formatStatValue(value: number, digits = 3): string {
  return Number.isFinite(value) ? value.toFixed(digits) : "-"
}
