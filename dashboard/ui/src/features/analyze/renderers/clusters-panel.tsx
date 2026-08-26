import { useCallback, useMemo, type FC } from "react"

import { escapeHtml } from "@/shared/escape-html"
import { Badge } from "@e-infra/design-system"

import type { ClustersAnalysis } from "../analysis-types"
import { BarChart, HeatmapMatrix } from "../charts"

const MAX_VISIBLE_CLUSTERS = 20

const formatClusterLabel = (index: number, frame?: number) => {
  if (typeof frame === "number" && Number.isFinite(frame)) {
    return `Cluster ${index + 1} (frame ${frame})`
  }
  return `Cluster ${index + 1}`
}

const ClustersPanel: FC<{ data: ClustersAnalysis }> = ({ data }) => {
  const clusters = useMemo(() => (Array.isArray(data?.clusters) ? data.clusters : []), [data?.clusters])
  const hasClusters = clusters.length > 0
  const transitions = useMemo(() => (Array.isArray(data.transitions) ? data.transitions : []), [data.transitions])

  const clusterSizes = useMemo(() => {
    if (!hasClusters) {
      return [] as Array<{ label: string; size: number; index: number }>
    }
    return clusters.map((cluster, index) => ({
      label: formatClusterLabel(index, cluster?.main),
      size: Array.isArray(cluster?.frames) ? cluster.frames.length : 0,
      index,
    }))
  }, [clusters, hasClusters])

  const totalFrames = clusterSizes.reduce((sum, entry) => sum + entry.size, 0)
  const topClusters = useMemo(() => {
    return clusterSizes
      .slice()
      .sort((a, b) => b.size - a.size)
      .slice(0, MAX_VISIBLE_CLUSTERS)
  }, [clusterSizes])

  const barCategories = topClusters.map((entry) => entry.label)
  const barSeries = [
    {
      name: "Frames",
      data: topClusters.map((entry) => entry.size),
    },
  ]

  const clusterIndexById = useMemo(() => {
    const map = new Map<number, number>()
    clusters.forEach((cluster, index) => {
      map.set(index, index)
      if (typeof cluster?.main === "number" && Number.isFinite(cluster.main)) {
        map.set(cluster.main, index)
      }
    })
    return map
  }, [clusters])

  const resolveClusterIndex = useCallback(
    (value: number | undefined) => {
      if (typeof value !== "number" || !Number.isFinite(value)) return undefined
      if (value >= 0 && value < clusters.length) return value
      return clusterIndexById.get(value)
    },
    [clusterIndexById, clusters.length]
  )

  const transitionHeatmap = useMemo(() => {
    if (!hasClusters) {
      return null
    }
    const size = clusters.length

    const matrix = Array.from({ length: size }, () => Array.from({ length: size }, () => 0))

    transitions.forEach((transition) => {
      const fromIdx = resolveClusterIndex(transition?.from)
      const toIdx = resolveClusterIndex(transition?.to)
      if (fromIdx === null || fromIdx === undefined || toIdx === null || toIdx === undefined) return
      const count = typeof transition?.count === "number" && Number.isFinite(transition.count) ? transition.count : 0
      matrix[fromIdx][toIdx] += count
    })

    const triples: Array<[number, number, number]> = []
    for (let row = 0; row < size; row += 1) {
      for (let col = 0; col < size; col += 1) {
        triples.push([col, row, matrix[row][col]])
      }
    }

    const labels = clusters.map((cluster, index) => formatClusterLabel(index, cluster?.main))

    return { triples, labels }
  }, [clusters, transitions, resolveClusterIndex, hasClusters])

  const topTransitions = useMemo(() => {
    if (!hasClusters) {
      return [] as Array<{
        count: number
        from: number | undefined
        to: number | undefined
      }>
    }
    return transitions
      .filter(
        (transition) =>
          typeof transition?.count === "number" && Number.isFinite(transition.count) && transition.count > 0
      )
      .map((transition) => ({
        count: transition.count,
        from: resolveClusterIndex(transition.from),
        to: resolveClusterIndex(transition.to),
      }))
      .filter((entry) => entry.from !== null && entry.from !== undefined && entry.to !== null && entry.to !== undefined)
      .sort((a, b) => b.count - a.count)
      .slice(0, 6)
  }, [transitions, resolveClusterIndex, hasClusters])

  const labels = clusters.map((cluster, index) => formatClusterLabel(index, cluster?.main))

  if (!hasClusters) {
    return (
      <div className="text-text-muted flex h-full items-center justify-center text-sm">
        No clustering data available.
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="space-y-1">
        <p className="text-sm font-medium">Conformational clustering</p>
        <p className="text-text-muted text-xs">
          Review cluster populations and transition counts derived from the RMSD-based clustering run.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="border-border rounded-md border p-3">
          <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Clusters</p>
          <p className="text-base font-semibold">{clusters.length}</p>
        </div>
        <div className="border-border rounded-md border p-3">
          <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Total frames</p>
          <p className="text-base font-semibold">{totalFrames}</p>
        </div>
        <div className="border-border rounded-md border p-3">
          <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Cutoff</p>
          <p className="text-base font-semibold">{typeof data.cutoff === "number" ? data.cutoff : "N/A"}</p>
        </div>
        <div className="border-border rounded-md border p-3">
          <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Version</p>
          <p className="text-base font-semibold">{data.version || "N/A"}</p>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="border-border rounded-lg border p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-sm font-medium">Cluster populations</p>
              <p className="text-text-muted text-xs">Top {topClusters.length} clusters ranked by number of frames.</p>
            </div>
            {clusterSizes.length > MAX_VISIBLE_CLUSTERS && (
              <Badge variant="outline">Showing top {MAX_VISIBLE_CLUSTERS}</Badge>
            )}
          </div>
          <div className="mt-4 h-105">
            <BarChart categories={barCategories} series={barSeries} />
          </div>
        </div>

        <div className="border-border rounded-lg border p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-sm font-medium">Transition counts</p>
              <p className="text-text-muted text-xs">
                Rows represent origin clusters; columns represent destination clusters.
              </p>
            </div>
            <Badge variant="outline">{transitions.length} transitions</Badge>
          </div>
          <div className="mt-4 h-105">
            {transitionHeatmap?.triples.length ? (
              <HeatmapMatrix
                data={transitionHeatmap.triples}
                xLabels={labels}
                yLabels={labels}
                title="Transitions"
                tooltipFormatter={(context) => {
                  // Labels come from the analysis payload — escape before innerHTML.
                  const fromLabel = escapeHtml(labels[context.yIndex] ?? `Cluster ${context.yIndex + 1}`)
                  const toLabel = escapeHtml(labels[context.xIndex] ?? `Cluster ${context.xIndex + 1}`)
                  return `<div><strong>${fromLabel} → ${toLabel}</strong><br/>Count: ${context.value}</div>`
                }}
                valueRange={{ min: 0 }}
              />
            ) : (
              <div className="border-border text-text-muted flex h-full items-center justify-center rounded-lg border border-dashed px-4 text-sm">
                No transition records.
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="border-border rounded-lg border p-4">
        <p className="text-sm font-medium">Most frequent transitions</p>
        <p className="text-text-muted text-xs">Highest-count transitions based on the provided transition table.</p>
        <div className="mt-3 space-y-2">
          {topTransitions.length ? (
            topTransitions.map((entry, idx) => (
              <div
                key={`${entry.from}-${entry.to}-${idx}`}
                className="border-border flex items-center justify-between rounded-md border px-3 py-2 text-sm"
              >
                <span>
                  {labels[entry.from ?? 0] ?? `Cluster ${Number(entry.from) + 1}`} →{" "}
                  {labels[entry.to ?? 0] ?? `Cluster ${Number(entry.to) + 1}`}
                </span>
                <span className="font-mono text-xs">{entry.count}</span>
              </div>
            ))
          ) : (
            <div className="border-border text-text-muted rounded-md border border-dashed px-3 py-4 text-sm">
              No transitions exceed the reporting threshold.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default ClustersPanel
