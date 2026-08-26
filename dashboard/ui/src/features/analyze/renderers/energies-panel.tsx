import { useEffect, useMemo, useState, type FC } from "react"

import { Badge, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@e-infra/design-system"

import type { EnergiesAgentData, EnergiesAnalysis } from "../analysis-types"
import { LineChart, StackedAreaChart } from "../charts"
import type { LineSeries } from "../charts/line-chart"
import type { StackedSeries } from "../charts/stacked-area-chart"
import { buildLineSeries, buildStackedSeries, sanitizeNumericArray } from "./utils"

const ENERGY_LABELS = {
  es: "Electrostatic",
  vdw: "Van der Waals",
  both: "Electrostatic + VdW",
} as const

const STAGE_OPTIONS = [
  {
    key: "overall",
    label: "Overall",
    fields: { es: "es", vdw: "vdw", both: "both" },
  },
  {
    key: "initial",
    label: "Initial",
    fields: { es: "ies", vdw: "ivdw", both: "iboth" },
  },
  {
    key: "final",
    label: "Final",
    fields: { es: "fes", vdw: "fvdw", both: "fboth" },
  },
] as const

type StageKey = (typeof STAGE_OPTIONS)[number]["key"]

type NormalizedAgent = {
  labels: string[]
  es: number[]
  ies: number[]
  fes: number[]
  vdw: number[]
  ivdw: number[]
  fvdw: number[]
  both: number[]
  iboth: number[]
  fboth: number[]
}

type EnergiesEntry = {
  id: string
  label: string
  agent1: NormalizedAgent
  agent2: NormalizedAgent
}

const sanitizeStringArray = (values: unknown): string[] => {
  if (!Array.isArray(values)) return []
  return values
    .map((value) => (typeof value === "string" ? value : null))
    .filter((value): value is string => Boolean(value))
}

const normalizeAgent = (agent: EnergiesAgentData | undefined): NormalizedAgent => {
  const labels = sanitizeStringArray(agent?.labels)
  const es = sanitizeNumericArray(agent?.es)
  const ies = sanitizeNumericArray(agent?.ies)
  const fes = sanitizeNumericArray(agent?.fes)
  const vdw = sanitizeNumericArray(agent?.vdw)
  const ivdw = sanitizeNumericArray(agent?.ivdw)
  const fvdw = sanitizeNumericArray(agent?.fvdw)
  const both = sanitizeNumericArray(agent?.both)
  const iboth = sanitizeNumericArray(agent?.iboth)
  const fboth = sanitizeNumericArray(agent?.fboth)

  const seriesLengths = [
    es.length,
    ies.length,
    fes.length,
    vdw.length,
    ivdw.length,
    fvdw.length,
    both.length,
    iboth.length,
    fboth.length,
  ].filter((length) => length > 0)
  const limit = seriesLengths.length ? Math.min(...seriesLengths) : labels.length
  const clampedLimit = limit > 0 ? limit : 0

  const trim = (values: number[]) => (clampedLimit ? values.slice(0, clampedLimit) : [])
  const buildLabels = (values: string[]) => {
    if (!clampedLimit) return values
    return Array.from({ length: clampedLimit }, (_, index) => {
      const label = values[index]
      return label && label.trim().length ? label.trim() : `Residue ${index + 1}`
    })
  }

  return {
    labels: buildLabels(labels),
    es: trim(es),
    ies: trim(ies),
    fes: trim(fes),
    vdw: trim(vdw),
    ivdw: trim(ivdw),
    fvdw: trim(fvdw),
    both: trim(both),
    iboth: trim(iboth),
    fboth: trim(fboth),
  }
}

const EnergiesPanel: FC<{ data: EnergiesAnalysis }> = ({ data }) => {
  const interactions = useMemo<EnergiesEntry[]>(() => {
    if (!Array.isArray(data?.data)) return []
    return data.data.map((entry, index) => ({
      id: entry?.name ?? `interaction-${index}`,
      label:
        typeof entry?.name === "string" && entry.name.trim().length ? entry.name.trim() : `Interaction ${index + 1}`,
      agent1: normalizeAgent(entry?.agent1),
      agent2: normalizeAgent(entry?.agent2),
    }))
  }, [data])

  const [interactionId, setInteractionId] = useState<string>(interactions[0]?.id ?? "")
  const [agentKey, setAgentKey] = useState<"agent1" | "agent2">("agent1")
  const [stage, setStage] = useState<StageKey>("overall")

  useEffect(() => {
    if (!interactions.length) return
    if (!interactions.some((entry) => entry.id === interactionId)) {
      setInteractionId(interactions[0]?.id ?? "")
    }
  }, [interactionId, interactions])

  const selectedInteraction = interactions.find((entry) => entry.id === interactionId) ?? interactions[0]
  const selectedAgent = selectedInteraction?.[agentKey]

  const labels = useMemo(() => selectedAgent?.labels ?? [], [selectedAgent])
  const xPositions = useMemo(() => labels.map((_, index) => index + 1), [labels])

  const stageConfig = STAGE_OPTIONS.find((option) => option.key === stage)

  const lineSeries = useMemo(() => {
    if (!selectedAgent || !stageConfig) return []
    const series = [
      buildLineSeries(
        ENERGY_LABELS.es,
        xPositions,
        selectedAgent[stageConfig.fields.es as keyof NormalizedAgent] as number[]
      ),
      buildLineSeries(
        ENERGY_LABELS.vdw,
        xPositions,
        selectedAgent[stageConfig.fields.vdw as keyof NormalizedAgent] as number[]
      ),
      buildLineSeries(
        ENERGY_LABELS.both,
        xPositions,
        selectedAgent[stageConfig.fields.both as keyof NormalizedAgent] as number[]
      ),
    ].filter((entry): entry is LineSeries => Boolean(entry))
    return series
  }, [selectedAgent, stageConfig, xPositions])

  const stackedSeries = useMemo(() => {
    if (!selectedAgent || !stageConfig) return []
    const series = [
      buildStackedSeries(
        ENERGY_LABELS.es,
        xPositions,
        selectedAgent[stageConfig.fields.es as keyof NormalizedAgent] as number[]
      ),
      buildStackedSeries(
        ENERGY_LABELS.vdw,
        xPositions,
        selectedAgent[stageConfig.fields.vdw as keyof NormalizedAgent] as number[]
      ),
      buildStackedSeries(
        ENERGY_LABELS.both,
        xPositions,
        selectedAgent[stageConfig.fields.both as keyof NormalizedAgent] as number[]
      ),
    ].filter((entry): entry is StackedSeries => Boolean(entry))
    return series
  }, [selectedAgent, stageConfig, xPositions])

  const combinedEntries = useMemo(() => {
    if (!selectedAgent || !stageConfig) return []
    const values = (selectedAgent[stageConfig.fields.both as keyof NormalizedAgent] as number[]) || []
    return values.map((value, index) => ({
      index,
      label: labels[index] ?? `Residue ${index + 1}`,
      value,
    }))
  }, [labels, selectedAgent, stageConfig])

  const topContributors = useMemo(() => {
    if (!combinedEntries.length) return []
    return combinedEntries
      .slice()
      .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
      .slice(0, 6)
  }, [combinedEntries])

  if (!interactions.length) {
    return (
      <div className="text-text-muted flex h-full items-center justify-center text-sm">
        No energies analysis data available.
      </div>
    )
  }

  if (!selectedAgent || !stageConfig || !lineSeries.length) {
    return (
      <div className="text-text-muted flex h-full items-center justify-center text-sm">
        The selected interaction does not contain usable energy time series.
      </div>
    )
  }

  const formatStat = (value?: number) =>
    typeof value === "number" && Number.isFinite(value) ? value.toFixed(2) : "N/A"

  const stageLabel = stageConfig.label

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <p className="text-sm font-medium">Interaction energies</p>
          <p className="text-text-muted text-xs">
            Inspect per-residue electrostatic and Van der Waals contributions for each interaction agent.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Select value={interactionId} onValueChange={setInteractionId}>
            <SelectTrigger className="h-8 w-48 text-xs">
              <SelectValue placeholder="Interaction" />
            </SelectTrigger>
            <SelectContent>
              {interactions.map((entry) => (
                <SelectItem key={entry.id} value={entry.id}>
                  {entry.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={agentKey} onValueChange={(value) => setAgentKey(value as "agent1" | "agent2")}>
            <SelectTrigger className="h-8 w-40 text-xs">
              <SelectValue placeholder="Agent" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="agent1">Agent 1</SelectItem>
              <SelectItem value="agent2">Agent 2</SelectItem>
            </SelectContent>
          </Select>
          <Select value={stage} onValueChange={(value) => setStage(value as StageKey)}>
            <SelectTrigger className="h-8 w-40 text-xs">
              <SelectValue placeholder="Stage" />
            </SelectTrigger>
            <SelectContent>
              {STAGE_OPTIONS.map((option) => (
                <SelectItem key={option.key} value={option.key}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="border-border rounded-md border p-3">
          <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Residues</p>
          <p className="text-lg font-semibold">{labels.length}</p>
        </div>
        <div className="border-border rounded-md border p-3">
          <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Stage</p>
          <p className="text-lg font-semibold">{stageLabel}</p>
        </div>
        <div className="border-border rounded-md border p-3">
          <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Agent</p>
          <p className="text-lg font-semibold">{agentKey === "agent1" ? "Agent 1" : "Agent 2"}</p>
        </div>
        <div className="border-border rounded-md border p-3">
          <p className="text-text-muted/80 text-[11px] tracking-wide uppercase">Top |S|</p>
          <p className="text-lg font-semibold">
            {formatStat(Math.max(...topContributors.map((entry) => Math.abs(entry.value)), 0))}
          </p>
        </div>
      </div>

      <div className="border-border flex min-h-80 flex-col rounded-lg border p-4">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">{stageLabel} energies per residue</p>
            <p className="text-text-muted text-xs">
              Three-component line chart for electrostatic, Van der Waals, and their sum.
            </p>
          </div>
          <Badge variant="outline" className="text-[11px]">
            {labels.length} samples
          </Badge>
        </div>
        <div className="min-h-65 flex-1">
          <LineChart series={lineSeries} xLabel="Residue index" yLabel="Energy (kcal/mol)" showLegend yScale />
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="border-border flex min-h-70 flex-col rounded-lg border p-4">
          <p className="mb-3 text-sm font-medium">Stacked contribution</p>
          <div className="min-h-55 flex-1">
            {stackedSeries.length ? (
              <StackedAreaChart series={stackedSeries} xLabel="Residue index" yLabel="Energy (kcal/mol)" />
            ) : (
              <div className="text-text-muted flex h-full items-center justify-center text-sm">
                No stacked data available for this stage.
              </div>
            )}
          </div>
        </div>
        <div className="border-border rounded-lg border p-4">
          <p className="mb-2 text-sm font-medium">Top absolute contributors</p>
          {topContributors.length ? (
            <ul className="space-y-2 text-sm">
              {topContributors.map((entry) => (
                <li key={`${entry.label}-${entry.index}`} className="flex items-center justify-between">
                  <span className="text-text-muted">
                    {entry.index + 1}. {entry.label}
                  </span>
                  <span className="font-semibold">{formatStat(entry.value)} kcal/mol</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-text-muted text-xs">Unable to compute contributor ranking for this selection.</p>
          )}
        </div>
      </div>
    </div>
  )
}

export default EnergiesPanel
