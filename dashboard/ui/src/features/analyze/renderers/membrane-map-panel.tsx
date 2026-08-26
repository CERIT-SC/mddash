import { useEffect, useMemo, useState, type FC } from "react"

import { escapeHtml } from "@/shared/escape-html"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@e-infra/design-system"

import type { MembraneMapAnalysis } from "../analysis-types"
import EChartsBase from "../charts/echarts-base"
import type { EChartsOption } from "../charts/echarts-setup"
import LabeledList from "./labeled-list"

const sanitizeIndexList = (values: unknown): number[] => {
  if (!Array.isArray(values)) return []
  return values
    .map((value) => (typeof value === "number" && Number.isFinite(value) ? Math.trunc(value) : null))
    .filter((value): value is number => value !== null)
}

const formatResidueList = (values: number[]): string => {
  if (!values.length) return "No indices"
  const preview = values.slice(0, 12).join(", ")
  const remaining = values.length - 12
  return remaining > 0 ? `${preview}, +${remaining} more` : preview
}

const fallbackLabel = (key: string, index: number) => (key && key.trim().length ? key : `Membrane ${index + 1}`)

const listForDisplay = (values: number[]): string[] =>
  values.length ? values.map((value) => value.toString()) : ["None recorded"]

type NormalizedMembrane = {
  id: string
  label: string
  leaflets: {
    top: number[]
    bot: number[]
  }
  polarAtoms: {
    top: number[]
    bot: number[]
  }
}

type ChartDatum = {
  value: number
  residues: number[]
}

const normalizeMembranes = (analysis: MembraneMapAnalysis): NormalizedMembrane[] => {
  if (!analysis.mems || typeof analysis.mems !== "object") return []
  return Object.entries(analysis.mems).map(([key, entry], index) => {
    const id = key && key.trim().length ? key : `mem-${index + 1}`
    const leaflets = entry?.leaflets ?? { top: [], bot: [] }
    const polar = entry?.polar_atoms ?? { top: [], bot: [] }
    return {
      id,
      label: fallbackLabel(key, index),
      leaflets: {
        top: sanitizeIndexList(leaflets.top),
        bot: sanitizeIndexList(leaflets.bot),
      },
      polarAtoms: {
        top: sanitizeIndexList(polar.top),
        bot: sanitizeIndexList(polar.bot),
      },
    }
  })
}

const buildTooltipFormatter =
  (categories: string[]) =>
  (payload: unknown): string => {
    const entries = Array.isArray(payload) ? payload : [payload]
    const normalized = entries.filter(Boolean) as Array<{
      axisValueLabel?: string
      dataIndex?: number
      marker?: string
      seriesName?: string
      value?: number
      data?: ChartDatum
    }>

    if (!normalized.length) return ""

    // Categories/series names derive from payload membrane names — escape them;
    // marker is ECharts' generated color-dot HTML and must stay markup.
    const header = escapeHtml(normalized[0].axisValueLabel ?? categories[normalized[0].dataIndex ?? 0] ?? "Membrane")

    const rows = normalized
      .map((entry) => {
        const residues = Array.isArray(entry.data?.residues) ? (entry.data?.residues ?? []) : []
        const value = typeof entry.value === "number" ? entry.value : residues.length
        return (
          `${entry.marker ?? ""}${escapeHtml(entry.seriesName)}: ${value}<br/>` +
          `<span style="margin-left:12px;font-size:11px;color:#94a3b8;">${formatResidueList(residues)}</span>`
        )
      })
      .join("<br/>")

    return `<div><strong>${header}</strong><br/>${rows}</div>`
  }

const MembraneMapAnalysisPanel: FC<{ data: MembraneMapAnalysis }> = ({ data }) => {
  const membranes = useMemo(() => normalizeMembranes(data), [data])
  const unassignedLipids = useMemo(() => sanitizeIndexList(data.no_mem_lipid), [data.no_mem_lipid])
  const hasMultipleMembranes = membranes.length > 1
  const [selectedMembrane, setSelectedMembrane] = useState<string>("all")

  useEffect(() => {
    if (!hasMultipleMembranes && selectedMembrane !== "all") {
      setSelectedMembrane("all")
      return
    }
    if (
      hasMultipleMembranes &&
      selectedMembrane !== "all" &&
      !membranes.some((membrane) => membrane.id === selectedMembrane)
    ) {
      setSelectedMembrane("all")
    }
  }, [hasMultipleMembranes, membranes, selectedMembrane])

  const filteredMembranes = useMemo(() => {
    if (!hasMultipleMembranes || selectedMembrane === "all") {
      return membranes
    }
    return membranes.filter((membrane) => membrane.id === selectedMembrane)
  }, [hasMultipleMembranes, membranes, selectedMembrane])

  const stats = useMemo(() => {
    return filteredMembranes.reduce(
      (acc, membrane) => {
        acc.top += membrane.leaflets.top.length
        acc.bottom += membrane.leaflets.bot.length
        return acc
      },
      { top: 0, bottom: 0 }
    )
  }, [filteredMembranes])

  const chartOption = useMemo<EChartsOption | undefined>(() => {
    if (!filteredMembranes.length) return undefined
    const categories = filteredMembranes.map((membrane) => membrane.label)
    return {
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        borderWidth: 0,
        backgroundColor: "#0f172a",
        textStyle: { color: "#f8fafc" },
        formatter: buildTooltipFormatter(categories),
      },
      legend: {},
      grid: { left: 70, right: 20, top: 40, bottom: 50 },
      xAxis: {
        type: "category",
        data: categories,
        axisLabel: { rotate: categories.length > 4 ? 20 : 0 },
      },
      yAxis: { type: "value", name: "Lipid count" },
      series: [
        {
          name: "Top leaflet",
          type: "bar",
          stack: "leaflets",
          emphasis: { focus: "series" },
          data: filteredMembranes.map<ChartDatum>((membrane) => ({
            value: membrane.leaflets.top.length,
            residues: membrane.leaflets.top,
          })),
        },
        {
          name: "Bottom leaflet",
          type: "bar",
          stack: "leaflets",
          emphasis: { focus: "series" },
          data: filteredMembranes.map<ChartDatum>((membrane) => ({
            value: membrane.leaflets.bot.length,
            residues: membrane.leaflets.bot,
          })),
        },
      ],
    } satisfies EChartsOption
  }, [filteredMembranes])

  const hasAnyData = membranes.length > 0 || unassignedLipids.length > 0

  if (!hasAnyData) {
    return (
      <div className="text-text-muted flex h-full items-center justify-center text-sm">
        No membrane map analysis data available.
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium">Membrane leaflet composition</p>
          <p className="text-text-muted text-xs">Stacked counts of top vs bottom leaflet assignments per membrane</p>
        </div>
        {hasMultipleMembranes && (
          <Select value={selectedMembrane} onValueChange={setSelectedMembrane}>
            <SelectTrigger className="h-9 w-56 text-sm">
              <SelectValue placeholder="Filter membranes" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All membranes</SelectItem>
              {membranes.map((membrane) => (
                <SelectItem key={membrane.id} value={membrane.id}>
                  {membrane.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-5">
        <div className="border-border flex min-h-80 flex-col gap-4 rounded-lg border p-4 lg:col-span-3">
          <div className="grid gap-2 sm:grid-cols-3">
            <div className="border-border rounded-md border p-3">
              <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Membranes shown</p>
              <p className="text-lg font-semibold">{filteredMembranes.length || 0}</p>
            </div>
            <div className="border-border rounded-md border p-3">
              <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Top lipids</p>
              <p className="text-lg font-semibold">{stats.top}</p>
            </div>
            <div className="border-border rounded-md border p-3">
              <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Bottom lipids</p>
              <p className="text-lg font-semibold">{stats.bottom}</p>
            </div>
          </div>
          <div className="h-80 min-h-0 flex-1">
            {chartOption ? (
              <EChartsBase option={chartOption} style={{ width: "100%", height: "100%" }} />
            ) : (
              <div className="text-text-muted flex h-full items-center justify-center text-sm">
                No leaflet assignments provided for the selected membrane.
              </div>
            )}
          </div>
        </div>
        <div className="flex flex-col gap-4 lg:col-span-2">
          <div className="border-border space-y-4 rounded-lg border p-4">
            <div>
              <p className="text-sm font-medium">Polar atom indices</p>
              <p className="text-text-muted text-xs">Per-leaflet polar selections to validate leaflet detection</p>
            </div>
            {filteredMembranes.map((membrane) => (
              <div key={membrane.id} className="space-y-2">
                {hasMultipleMembranes && (
                  <p className="text-text-muted text-[11px] tracking-wide uppercase">{membrane.label}</p>
                )}
                <LabeledList
                  label="Top leaflet"
                  list={listForDisplay(membrane.polarAtoms.top)}
                  orientation="vertical"
                  maxVisibleItems={8}
                />
                <LabeledList
                  label="Bottom leaflet"
                  list={listForDisplay(membrane.polarAtoms.bot)}
                  orientation="vertical"
                  maxVisibleItems={8}
                />
              </div>
            ))}
            {!filteredMembranes.length && (
              <p className="text-text-muted text-xs">No polar atom assignments available for the selected membrane.</p>
            )}
          </div>
          <div className="border-border space-y-3 rounded-lg border p-4">
            <div>
              <p className="text-sm font-medium">Unassigned lipids</p>
              <p className="text-text-muted text-xs">Lipids without a leaflet assignment (`no_mem_lipid` bucket)</p>
            </div>
            {unassignedLipids.length ? (
              <LabeledList
                label="Indices"
                list={listForDisplay(unassignedLipids)}
                orientation="vertical"
                maxVisibleItems={10}
              />
            ) : (
              <p className="text-text-muted text-xs">No unassigned lipids reported.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default MembraneMapAnalysisPanel
