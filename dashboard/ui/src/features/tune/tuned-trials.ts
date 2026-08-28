import { Engine, JobStatus, type TunerTrial } from "@/api/generated/models"
import { z } from "zod"

// TunerTrial config fields are engine-shaped and left untyped by the API —
// this module is the Zod runtime boundary into typed table rows.

const baseTrialSchema = z.object({
  id: z.string(),
  status: z.enum(JobStatus),
  performance: z.number().nullish(),
  estimated_time: z.number().nullish(),
  estimated_cost: z.number().nullish(),
})

// Degrade per field: one bad value blanks only its own cell.
function numField(raw: TunerTrial, key: string): number | null {
  const parsed = z.number().safeParse(raw[key])
  return parsed.success ? parsed.data : null
}

function strField(raw: TunerTrial, key: string): string | null {
  const parsed = z.string().safeParse(raw[key])
  return parsed.success ? parsed.data : null
}

export type TrialRow = {
  id: string
  status: JobStatus
  /** Tuning throughput in ns/day; null until the trial reports a result. */
  performance: number | null
  /** Estimated wall-clock hours for the full production simulation. */
  estTimeHours: number | null
  /** Estimated compute cost for the full production simulation. */
  estCost: number | null
  np: number | null
  ntomp: number | null
  /** GMX: device for long-range electrostatics ("cpu" | "gpu" in practice). */
  pme: string | null
  /** GMX: device for short-range non-bonded interactions. */
  nb: string | null
  /** AMBER: pmemd binary variant. */
  binary: string | null
  /** AMBER: Ewald summation preset. */
  ewald: string | null
}

/** Bad base fields drop the row; bad engine fields blank only their own cell. */
export function parseTrial(engine: Engine, raw: TunerTrial): TrialRow | null {
  const base = baseTrialSchema.safeParse(raw)
  if (!base.success) return null
  const gmx = engine !== Engine.AMBER
  return {
    id: base.data.id,
    status: base.data.status,
    performance: base.data.performance ?? null,
    estTimeHours: base.data.estimated_time ?? null,
    estCost: base.data.estimated_cost ?? null,
    np: numField(raw, "np"),
    ntomp: numField(raw, "ntomp"),
    pme: gmx ? strField(raw, "pme") : null,
    nb: gmx ? strField(raw, "nb") : null,
    binary: gmx ? null : strField(raw, "binary"),
    ewald: gmx ? null : strField(raw, "ewald"),
  }
}

export function parseTrials(engine: Engine, raw: TunerTrial[] | undefined): TrialRow[] {
  return (raw ?? []).map((trial) => parseTrial(engine, trial)).filter((row) => row !== null)
}

export function selectable(row: TrialRow): boolean {
  return row.status === JobStatus.FINISHED && row.performance !== null
}

type Suggestions = {
  /** Highest measured performance — the tuner's speed champion. */
  fastestId: string | null
  /** Lowest estimated production cost; may coincide with fastestId. */
  ecoId: string | null
}

/** SUGGESTED = fastest finished trial + cheapest with a known cost; may coincide. */
export function suggest(rows: TrialRow[]): Suggestions {
  let fastest: TrialRow | null = null
  let eco: TrialRow | null = null
  for (const row of rows) {
    if (!selectable(row)) continue
    if (fastest === null || row.performance! > fastest.performance!) fastest = row
    if (row.estCost !== null && (eco === null || row.estCost < eco.estCost!)) eco = row
  }
  return { fastestId: fastest?.id ?? null, ecoId: eco?.id ?? null }
}

/** Results by performance (best first); trials without a result keep arrival order below. */
export function sortTrials(rows: TrialRow[]): TrialRow[] {
  return [...rows].sort((a, b) => {
    if (a.performance === null || b.performance === null) {
      if (a.performance === b.performance) return 0
      return a.performance === null ? 1 : -1
    }
    return b.performance - a.performance
  })
}

/** "$2.60" → "$2.6", while tiny costs keep precision ("$0.04"). */
export function formatCost(cost: number): string {
  return `$${cost.toFixed(2).replace(/\.?0+$/, "")}`
}

export function formatHardware(value: string | null): string {
  return value === null ? "—" : value.toUpperCase()
}
