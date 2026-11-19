import { Step } from "@/api/generated/models"

/** Wizard steps in display order: the API declares the enum in that order, so counts and positions follow it. */
export const STEPS: readonly Step[] = Object.values(Step)

export const STEP_LABELS: Record<Step, string> = {
  setup: "Setup",
  configuration: "Configuration",
  simulation: "Simulation",
  analysis: "Analysis",
}
