import type { Simulation } from "@/api/generated/models"
import { missingRequiredRoles } from "@/features/simulation"

/** Manifest roles the MDPosit handoff needs: structure, topology (run input), trajectory. */
const MDPOSIT_ROLES = ["reference_structure", "run_input", "trajectory"] as const

/** Human-readable reason the MDPosit handoff can't be prepared for this
 * simulation, or null when it can — mirrors the check `_publish_mdposit` enforces. */
export function mdpositUnavailableReason(simulation: Simulation): string | null {
  if (!simulation.valid) return "The selected simulation is invalid. Repair it in the setup step."
  const missing = missingRequiredRoles(simulation, MDPOSIT_ROLES)
  if (missing.length > 0) return `Missing required files: ${missing.join(", ")}.`
  return null
}
