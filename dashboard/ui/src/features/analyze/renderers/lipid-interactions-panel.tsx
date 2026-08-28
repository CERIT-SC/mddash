import { useCallback, useEffect, useMemo, useState, type FC } from "react"

import { escapeHtml } from "@/shared/escape-html"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@e-infra/design-system"

import type { LipidInteractionAnalysis } from "../analysis-types"
import { HeatmapMatrix, type TooltipContext } from "../charts"
import LabeledList from "./labeled-list"

const sanitizeResidues = (values: unknown): number[] => {
  if (!Array.isArray(values)) return []
  return values
    .map((value, index) => (typeof value === "number" && Number.isFinite(value) ? Math.trunc(value) : index + 1))
    .filter((value): value is number => Number.isFinite(value))
}

const sanitizeLipidValues = (values: unknown, residueCount: number): number[] => {
  if (!Array.isArray(values)) return Array(residueCount).fill(0)
  const cleaned: number[] = Array.from({ length: residueCount }, (_, index) => {
    const value = values[index]
    return typeof value === "number" && Number.isFinite(value) ? value : 0
  })
  return cleaned
}

const formatResidueLabel = (index: number, fallback: number) =>
  Number.isFinite(index) ? `Residue ${index}` : `Residue ${fallback}`

const formatLipidLabel = (key: string): string => (key.length > 22 ? `${key.slice(0, 22)}…` : key)

const formatNumber = (value: number): string => value.toFixed(2)

type SortMode = "residue" | "max" | "total"

const LipidInteractionsPanel: FC<{ data: LipidInteractionAnalysis }> = ({ data }) => {
  const payload = data?.data

  const residueIndices = useMemo(() => sanitizeResidues(payload?.residue_indices), [payload?.residue_indices])

  const lipidEntries = useMemo(() => {
    if (!payload || typeof payload !== "object") return []
    return Object.entries(payload)
      .filter(([key]) => key !== "residue_indices")
      .map(([key, rawValues]) => ({
        key,
        values: sanitizeLipidValues(rawValues, residueIndices.length),
      }))
      .filter((entry) => entry.values.some((value) => value !== 0))
  }, [payload, residueIndices.length])

  const [lipidFilter, setLipidFilter] = useState<string>("all")
  const [sortMode, setSortMode] = useState<SortMode>("residue")

  useEffect(() => {
    if (lipidFilter === "all") return
    if (!lipidEntries.some((entry) => entry.key === lipidFilter)) {
      setLipidFilter("all")
    }
  }, [lipidEntries, lipidFilter])

  const activeLipids = useMemo(() => {
    if (lipidFilter === "all") return lipidEntries
    return lipidEntries.filter((entry) => entry.key === lipidFilter)
  }, [lipidEntries, lipidFilter])

  const residueOrder = useMemo(() => {
    const order = residueIndices.map((_, index) => index)
    if (!activeLipids.length) return order
    const rowSums = order.map((rowIndex) => activeLipids.reduce((sum, lipid) => sum + lipid.values[rowIndex], 0))
    const rowMax = order.map((rowIndex) => Math.max(...activeLipids.map((lipid) => lipid.values[rowIndex])))
    if (sortMode === "max") {
      return order.sort((a, b) => rowMax[b] - rowMax[a])
    }
    if (sortMode === "total") {
      return order.sort((a, b) => rowSums[b] - rowSums[a])
    }
    return order
  }, [activeLipids, residueIndices, sortMode])

  const columnTotals = useMemo(() => {
    return activeLipids.map((lipid) => lipid.values.reduce((sum, value) => sum + value, 0))
  }, [activeLipids])

  const heatmapData = useMemo(() => {
    const triples: Array<[number, number, number]> = []
    residueOrder.forEach((rowIndex, orderedRow) => {
      activeLipids.forEach((lipid, colIndex) => {
        triples.push([colIndex, orderedRow, lipid.values[rowIndex]])
      })
    })
    return triples
  }, [activeLipids, residueOrder])

  const yLabels = useMemo(
    () => residueOrder.map((rowIndex) => formatResidueLabel(residueIndices[rowIndex], rowIndex + 1)),
    [residueIndices, residueOrder]
  )

  const xLabels = useMemo(() => activeLipids.map((lipid) => formatLipidLabel(lipid.key)), [activeLipids])

  const tooltipFormatter = useCallback(
    ({ value, xIndex, yIndex, xLabel, yLabel }: TooltipContext) => {
      const total = columnTotals[xIndex] ?? 0
      const percent = total ? ((value / total) * 100).toFixed(1) : "0.0"
      // Labels come from the analysis payload — escape before innerHTML.
      const residueLabel = escapeHtml(yLabel ?? `Residue ${yIndex + 1}`)
      const lipidLabel = escapeHtml(xLabel ?? `Lipid ${xIndex + 1}`)
      return `<div><strong>${residueLabel}</strong><br/>${lipidLabel}: ${formatNumber(
        value
      )}<br/><span style="color:#94a3b8">${percent}% of ${lipidLabel}</span></div>`
    },
    [columnTotals]
  )

  const rowTotals = useMemo(() => {
    return residueOrder.map((rowIndex) => {
      const total = activeLipids.reduce((sum, lipid) => sum + lipid.values[rowIndex], 0)
      return {
        label: formatResidueLabel(residueIndices[rowIndex], rowIndex + 1),
        total,
      }
    })
  }, [activeLipids, residueIndices, residueOrder])

  const topResidues = useMemo(() => {
    return [...rowTotals]
      .sort((a, b) => b.total - a.total)
      .slice(0, 5)
      .map((entry) => `${entry.label} (${formatNumber(entry.total)})`)
  }, [rowTotals])

  const topLipids = useMemo(() => {
    return activeLipids
      .map((lipid, index) => ({
        label: formatLipidLabel(lipid.key),
        total: columnTotals[index] ?? 0,
      }))
      .sort((a, b) => b.total - a.total)
      .slice(0, 5)
      .map((entry) => `${entry.label} (${formatNumber(entry.total)})`)
  }, [activeLipids, columnTotals])

  const maxValue = useMemo(() => {
    const values = activeLipids.flatMap((lipid) => lipid.values)
    if (!values.length) return 0
    return Math.max(...values)
  }, [activeLipids])

  if (!residueIndices.length || !lipidEntries.length) {
    return (
      <div className="text-text-muted flex h-full items-center justify-center text-sm">
        No lipid interaction analysis data available.
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="border-border rounded-md border p-3">
          <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Residues tracked</p>
          <p className="text-lg font-semibold">{residueIndices.length}</p>
        </div>
        <div className="border-border rounded-md border p-3">
          <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Lipid species</p>
          <p className="text-lg font-semibold">{lipidEntries.length}</p>
        </div>
        <div className="border-border rounded-md border p-3">
          <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Peak occupancy</p>
          <p className="text-lg font-semibold">{formatNumber(maxValue)}</p>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-5">
        <div className="border-border flex min-h-90 flex-col gap-4 rounded-lg border p-4 lg:col-span-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium">Residue × lipid occupancy</p>
              <p className="text-text-muted text-xs">
                Heatmap counts per residue with optional sorting and lipid filter
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Select value={sortMode} onValueChange={(value) => setSortMode(value as SortMode)}>
                <SelectTrigger className="h-9 w-40 text-xs">
                  <SelectValue placeholder="Sort" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="residue">Residue number</SelectItem>
                  <SelectItem value="max">Max occupancy</SelectItem>
                  <SelectItem value="total">Total occupancy</SelectItem>
                </SelectContent>
              </Select>
              <Select value={lipidFilter} onValueChange={setLipidFilter}>
                <SelectTrigger className="h-9 w-48 text-xs">
                  <SelectValue placeholder="Filter lipid" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All lipids</SelectItem>
                  {lipidEntries.map((entry) => (
                    <SelectItem key={entry.key} value={entry.key}>
                      {formatLipidLabel(entry.key)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="min-h-80 flex-1">
            {heatmapData.length ? (
              <HeatmapMatrix
                data={heatmapData}
                xLabels={xLabels}
                yLabels={yLabels}
                enableFilter
                tooltipFormatter={tooltipFormatter}
              />
            ) : (
              <div className="text-text-muted flex h-full items-center justify-center text-sm">
                No lipid data available for the selected filter.
              </div>
            )}
          </div>
        </div>
        <div className="flex flex-col gap-4 lg:col-span-2">
          <div className="border-border space-y-3 rounded-lg border p-4">
            <div>
              <p className="text-sm font-medium">Top interacting residues</p>
              <p className="text-text-muted text-xs">Ranked by cumulative lipid contact counts</p>
            </div>
            {topResidues.length ? (
              <LabeledList label="Residues" list={topResidues} orientation="vertical" maxVisibleItems={6} />
            ) : (
              <p className="text-text-muted text-xs">No residue interactions to highlight.</p>
            )}
          </div>
          <div className="border-border space-y-3 rounded-lg border p-4">
            <div>
              <p className="text-sm font-medium">Top lipid species</p>
              <p className="text-text-muted text-xs">Summed occupancies across all residues</p>
            </div>
            {topLipids.length ? (
              <LabeledList label="Lipids" list={topLipids} orientation="vertical" maxVisibleItems={6} />
            ) : (
              <p className="text-text-muted text-xs">No lipid species exceed the selected filter.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default LipidInteractionsPanel
