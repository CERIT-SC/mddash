import type { Engine } from "@/api/generated/models"

export const ENGINE_LABELS: Record<Engine, string> = {
  GMX: "GROMACS",
  AMBER: "AMBER",
}

/** Engine listing order; GMX workflows are preferred. */
export const ENGINE_ORDER: Engine[] = ["GMX", "AMBER"]

/** URL/tab values for engine filters. */
export const ENGINE_TAB_VALUES: Record<Engine, "gmx" | "amber"> = { GMX: "gmx", AMBER: "amber" }

export type EngineFilter = (typeof ENGINE_TAB_VALUES)[Engine]

/** Narrows unknown values (search params) to a filter; derived from ENGINE_TAB_VALUES. */
export function asEngineFilter(value: unknown): EngineFilter | undefined {
  return Object.values(ENGINE_TAB_VALUES).includes(value as EngineFilter) ? (value as EngineFilter) : undefined
}
