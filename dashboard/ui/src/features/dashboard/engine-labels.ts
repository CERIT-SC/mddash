import type { Experiment } from "@/api/generated/models"

export const ENGINE_LABELS: Record<Experiment["engine"], string> = {
  GMX: "GROMACS",
  AMBER: "AMBER",
}
