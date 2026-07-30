import type { JobStatus } from "@/util/types"

// Subset of GmxTunerTrial / AmberTunerTrial so both engines' trial arrays are accepted as-is.
export interface ClassifiableTrial {
  id: string
  status: JobStatus
  performance: number | null
  estimated_cost: number | null
}

export type TrialClass = "fastest" | "most-efficient" | "most-expensive"

type WithPerformance = ClassifiableTrial & { performance: number }
type WithCost = ClassifiableTrial & { estimated_cost: number }

const maxBy = <T>(items: T[], value: (t: T) => number): T | null =>
  items.reduce<T | null>((best, t) => (best === null || value(t) > value(best) ? t : best), null)

const minBy = <T>(items: T[], value: (t: T) => number): T | null =>
  items.reduce<T | null>((best, t) => (best === null || value(t) < value(best) ? t : best), null)

export function computeTrialClasses(trials: ClassifiableTrial[]): Map<string, TrialClass[]> {
  const finishedWithPerformance = trials.filter(
    (t): t is WithPerformance => t.status === "FINISHED" && t.performance !== null
  )
  const finishedWithCost = trials.filter((t): t is WithCost => t.status === "FINISHED" && t.estimated_cost !== null)

  const classes = new Map<string, TrialClass[]>()
  const grant = (trial: ClassifiableTrial, cls: TrialClass) =>
    classes.set(trial.id, [...(classes.get(trial.id) ?? []), cls])

  const fastest = maxBy(finishedWithPerformance, (t) => t.performance)
  if (fastest) grant(fastest, "fastest")

  const cheapest = minBy(finishedWithCost, (t) => t.estimated_cost)
  if (cheapest) grant(cheapest, "most-efficient")

  const priciest = maxBy(finishedWithCost, (t) => t.estimated_cost)
  // skip when it equals the cheapest trial (e.g. a single finished trial)
  if (priciest && priciest.id !== cheapest?.id) grant(priciest, "most-expensive")

  return classes
}
