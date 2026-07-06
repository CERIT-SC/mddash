import { Engine } from "./const"
import type { Simulation } from "./types"

const SIMULATION_SUFFIX = ".simulation.json"

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

function normalizePath(path: string): string[] {
  return path.split("/").filter(Boolean)
}

function dirname(path: string): string {
  const index = path.lastIndexOf("/")
  return index === -1 ? "" : path.slice(0, index)
}

export function safeDefaultSimulationPath(name: string): string {
  const safeName = name.split(/[\\/]/).filter(Boolean).pop() || "simulation"
  return `production/${safeName}${SIMULATION_SUFFIX}`
}

export function experimentPathToManifestRelative(filePath: string, simulationPath: string): string {
  if (!filePath) return ""

  const from = normalizePath(dirname(simulationPath))
  const to = normalizePath(filePath)
  let common = 0

  while (common < from.length && common < to.length && from[common] === to[common]) {
    common += 1
  }

  return [...from.slice(common).map(() => ".."), ...to.slice(common)].join("/") || "."
}
