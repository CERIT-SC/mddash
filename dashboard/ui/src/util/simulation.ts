import { Engine } from "./const"
import type { Simulation } from "./types"

const REQUIRED_LAUNCH_ROLES: Record<Engine, string[]> = {
  [Engine.GMX]: ["topology"],
  [Engine.AMBER]: ["topology", "coordinates", "control"],
}

const REQUIRED_ANALYSIS_ROLES: Record<Engine, string[]> = {
  [Engine.GMX]: ["topology", "structure", "trajectory"],
  [Engine.AMBER]: ["topology", "trajectory"],
}

const REQUIRED_MDPOSIT_ROLES = ["structure", "topology", "trajectory"]

export function missingSimulationRoles(simulation: Simulation | null, roles: string[]): string[] {
  if (!simulation) return roles
  return roles.filter((role) => simulation.missing_files.includes(role) || !simulation.files[role])
}

export function simulationUnavailableReason(simulation: Simulation | null, requiredRoles: string[]): string | null {
  if (!simulation) return "Select a simulation first."
  if (!simulation.valid) return "Selected simulation is invalid."

  const missingRoles = missingSimulationRoles(simulation, requiredRoles)
  if (missingRoles.length > 0) return `Missing required files: ${missingRoles.join(", ")}.`

  return null
}

export function simulationLaunchUnavailableReason(simulation: Simulation | null, engine: Engine): string | null {
  return simulationUnavailableReason(simulation, REQUIRED_LAUNCH_ROLES[engine])
}

export function simulationAnalysisUnavailableReason(simulation: Simulation | null, engine: Engine): string | null {
  return simulationUnavailableReason(simulation, REQUIRED_ANALYSIS_ROLES[engine])
}

export function simulationMdpositUnavailableReason(simulation: Simulation | null): string | null {
  return simulationUnavailableReason(simulation, REQUIRED_MDPOSIT_ROLES)
}
