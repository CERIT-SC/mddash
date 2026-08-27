import { type Simulation } from "@/api/generated/models"
import { missingRequiredRoles } from "@/features/simulation"

/** Working-structure roles every analysis needs regardless of engine. */
const ANALYSIS_ROLES = ["reference_structure", "trajectory"] as const

/**
 * Human-readable reason the analysis step can't run for this simulation, or
 * null when it can. Mirrors the manifest availability check the setup step
 * enforces for the run.
 */
export function analysisUnavailableReason(simulation: Simulation): string | null {
  if (!simulation.valid) return "The selected simulation is invalid. Repair it in the setup step."
  const missing = missingRequiredRoles(simulation, ANALYSIS_ROLES)
  if (missing.length > 0) return `Missing required files: ${missing.join(", ")}.`
  return null
}
