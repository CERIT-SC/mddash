import { useEffect, useMemo, useState, type FC } from "react"

import type { InteractionData } from "@/util/analysis-types"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { downsampleMatrix, HeatmapMatrix } from "@/components/charts"

const formatLabel = (label: unknown, fallback: string) =>
  typeof label === "string" && label.trim().length ? label.trim() : fallback

const normalizeArray = (values: unknown): number[] =>
  Array.isArray(values)
    ? values.filter((value): value is number => typeof value === "number" && Number.isFinite(value))
    : []

type InteractionEntry = {
  id: string
  label: string
  agent1: string
  agent2: string
  residues1: number[]
  residues2: number[]
  interfaceResidues1: number[]
  interfaceResidues2: number[]
  atoms1: number[]
  atoms2: number[]
  interfaceAtoms1: number[]
  interfaceAtoms2: number[]
}

const buildMatrix = (entry: InteractionEntry): number[][] => {
  if (!entry.residues1.length || !entry.residues2.length) return []
  const interfaceSet1 = new Set(entry.interfaceResidues1)
  const interfaceSet2 = new Set(entry.interfaceResidues2)
  return entry.residues2.map((residue2) =>
    entry.residues1.map((residue1) => {
      const value = (interfaceSet1.has(residue1) ? 2 : 0) + (interfaceSet2.has(residue2) ? 1 : 0)
      return value
    })
  )
}

const toHeatmapPayload = (matrix: number[][]) => {
  if (!matrix.length) {
    return {
      data: [] as Array<[number, number, number]>,
      xLabels: [] as string[],
      yLabels: [] as string[],
    }
  }

  const { matrix: reduced, rowPositions, colPositions } = downsampleMatrix(matrix)

  const data: Array<[number, number, number]> = []
  reduced.forEach((row, rowIndex) => {
    row.forEach((value, colIndex) => {
      const safe = typeof value === "number" && Number.isFinite(value) ? value : 0
      data.push([colIndex, rowIndex, safe])
    })
  })

  const formatRange = (prefix: string, start: number, end: number) =>
    start === end ? `${prefix} ${start + 1}` : `${prefix} ${start + 1}-${end + 1}`

  return {
    data,
    xLabels: colPositions.map(({ start, end }) => formatRange("Agent 1", start, end)),
    yLabels: rowPositions.map(({ start, end }) => formatRange("Agent 2", start, end)),
  }
}

const chunkList = (values: readonly number[], label: string, size = 15) =>
  values.slice(0, size).map((value) => `${label} ${value}`)

const resolveList = (residues: number[], atoms: number[], fallbackLabel: string) => {
  if (residues.length) {
    return { values: residues, label: "Residue" } as const
  }
  if (atoms.length) {
    return { values: atoms, label: "Atom" } as const
  }
  return { values: [], label: fallbackLabel } as const
}

const InteractionsAnalysisPanel: FC<{
  data: InteractionData | InteractionData[]
}> = ({ data }) => {
  const entries = useMemo<InteractionEntry[]>(() => {
    const list = Array.isArray(data) ? data : [data]
    return list.filter(Boolean).map((entry, index) => ({
      id: `${index}`,
      label: formatLabel(entry?.name, `Interaction ${index + 1}`),
      agent1: formatLabel(entry?.agent_1, "Agent 1"),
      agent2: formatLabel(entry?.agent_2, "Agent 2"),
      residues1: normalizeArray(entry?.residue_indices_1),
      residues2: normalizeArray(entry?.residue_indices_2),
      interfaceResidues1: normalizeArray(entry?.interface_indices_1),
      interfaceResidues2: normalizeArray(entry?.interface_indices_2),
      atoms1: normalizeArray(entry?.atom_indices_1),
      atoms2: normalizeArray(entry?.atom_indices_2),
      interfaceAtoms1: normalizeArray(entry?.interface_atom_indices_1),
      interfaceAtoms2: normalizeArray(entry?.interface_atom_indices_2),
    }))
  }, [data])

  const [selectedId, setSelectedId] = useState(entries[0]?.id ?? "")

  useEffect(() => {
    if (!entries.length) return
    if (!entries.some((entry) => entry.id === selectedId)) {
      setSelectedId(entries[0]?.id ?? "")
    }
  }, [entries, selectedId])

  const selected = entries.find((entry) => entry.id === selectedId)
  const canRenderMatrix = Boolean(selected && selected.residues1.length && selected.residues2.length)
  const matrix = useMemo(() => (selected && canRenderMatrix ? buildMatrix(selected) : []), [selected, canRenderMatrix])
  const heatmap = useMemo(() => toHeatmapPayload(matrix), [matrix])

  if (!entries.length || !selected) {
    return (
      <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
        No interaction metadata available.
      </div>
    )
  }

  const agent1List = resolveList(selected.residues1, selected.atoms1, "Index")
  const agent2List = resolveList(selected.residues2, selected.atoms2, "Index")
  const interfaceList1 = resolveList(selected.interfaceResidues1, selected.interfaceAtoms1, agent1List.label)
  const interfaceList2 = resolveList(selected.interfaceResidues2, selected.interfaceAtoms2, agent2List.label)

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-sm font-medium">Interaction interfaces</p>
          <p className="text-muted-foreground text-xs">Highlights residues participating in each agent interface.</p>
        </div>
        {entries.length > 1 && (
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground text-xs">Interaction</span>
            <Select value={selectedId} onValueChange={setSelectedId}>
              <SelectTrigger className="h-8 w-48 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {entries.map((entry) => (
                  <SelectItem key={entry.id} value={entry.id}>
                    {entry.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="border-border/60 space-y-2 rounded-lg border p-4">
          <p className="text-sm font-semibold">{selected.label}</p>
          <div className="text-muted-foreground space-y-1 text-xs">
            <p>
              Agent 1 ({selected.agent1}): {agent1List.values.length} {""}
              {agent1List.label.toLowerCase()}s - Interface {interfaceList1.values.length}
            </p>
            <p>
              Agent 2 ({selected.agent2}): {agent2List.values.length} {""}
              {agent2List.label.toLowerCase()}s - Interface {interfaceList2.values.length}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground mb-1 text-xs tracking-wide uppercase">Interface residues snapshot</p>
            <div className="text-muted-foreground grid grid-cols-1 gap-2 text-xs">
              <div>
                <p className="text-foreground mb-1 font-medium">{selected.agent1}</p>
                <p>{chunkList(interfaceList1.values, interfaceList1.label).join(", ") || "None"}</p>
              </div>
              <div>
                <p className="text-foreground mb-1 font-medium">{selected.agent2}</p>
                <p>{chunkList(interfaceList2.values, interfaceList2.label).join(", ") || "None"}</p>
              </div>
            </div>
          </div>
        </div>
        <div className="border-border/60 flex min-h-[280px] flex-col rounded-lg border p-4 lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Interface coverage heatmap</p>
              <p className="text-muted-foreground text-xs">
                Value legend: 0 = none, 1 = agent 2 interface, 2 = agent 1 interface, 3 = both.
              </p>
            </div>
            <p className="text-muted-foreground text-xs">Cells: {heatmap.data.length}</p>
          </div>
          <div className="min-h-[240px] flex-1">
            {canRenderMatrix && heatmap.data.length ? (
              <HeatmapMatrix
                data={heatmap.data}
                xLabels={heatmap.xLabels}
                yLabels={heatmap.yLabels}
                title={`${selected.agent1} vs ${selected.agent2}`}
                enableFilter={false}
              />
            ) : (
              <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
                {canRenderMatrix
                  ? "Not enough interface data to build a heatmap."
                  : "Residue-level interface definitions were not provided, so the heatmap is unavailable for this interaction."}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default InteractionsAnalysisPanel
