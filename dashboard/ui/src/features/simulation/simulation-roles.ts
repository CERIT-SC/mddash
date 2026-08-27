import { Engine } from "@/api/generated/models"
import type { Simulation } from "@/api/generated/models"

export type FileRoleKey =
  "run_input" | "run_structure" | "reference_structure" | "trajectory" | "topology" | "coordinates" | "control"

/** `ext: null` marks free-text output paths; otherwise comma-separated picker extensions. */
export type RoleSpec = {
  key: FileRoleKey
  label: string
  help: string
  ext: string | null
  section: "input" | "output"
  required: boolean
}

export const ROLE_SPECS: Record<Engine, RoleSpec[]> = {
  [Engine.GMX]: [
    {
      key: "run_input",
      label: "Run input (.tpr)",
      help: "GROMACS run input file (.tpr) used to start the simulation.",
      ext: "tpr",
      section: "input",
      required: true,
    },
    {
      key: "reference_structure",
      label: "Reference structure",
      help: "Structure matching the trajectory atom set and order. Created by the setup notebook.",
      ext: "gro,pdb",
      section: "input",
      required: true,
    },
    {
      key: "trajectory",
      label: "Trajectory",
      help: "Trajectory file. Auto-filled from run input name.",
      ext: null,
      section: "output",
      required: true,
    },
    {
      key: "run_structure",
      label: "Final run structure",
      help: "Final coordinate snapshot from the run. Auto-filled from run input name.",
      ext: null,
      section: "output",
      required: false,
    },
  ],
  [Engine.AMBER]: [
    {
      key: "topology",
      label: "Topology",
      help: "AMBER topology file (.prmtop).",
      ext: "prmtop,parm7",
      section: "input",
      required: true,
    },
    {
      key: "control",
      label: "Run control",
      help: "AMBER run control file (.mdin). Outputs are written next to it.",
      ext: "mdin,in",
      section: "input",
      required: true,
    },
    {
      key: "coordinates",
      label: "Coordinates",
      help: "AMBER coordinate file (.rst7).",
      ext: "inpcrd,rst7",
      section: "input",
      required: true,
    },
    {
      key: "reference_structure",
      label: "Reference structure",
      help: "Structure matching the trajectory atom set and order. Created by the setup notebook.",
      ext: "gro,pdb",
      section: "input",
      required: true,
    },
    {
      key: "trajectory",
      label: "Trajectory",
      help: "Trajectory file. Auto-filled from run control name.",
      ext: null,
      section: "output",
      required: true,
    },
  ],
}

/** The role whose selection drives name/output auto-fill (AMBER writes next to control). */
export const DRIVER_ROLE: Record<Engine, FileRoleKey> = { [Engine.GMX]: "run_input", [Engine.AMBER]: "control" }

export const TRAJECTORY_EXTENSION: Record<Engine, string> = { [Engine.GMX]: "xtc", [Engine.AMBER]: "nc" }

export function dirname(path: string): string {
  const index = path.lastIndexOf("/")
  return index === -1 ? "" : path.slice(0, index)
}

export function stem(path: string): string {
  const name = path.split("/").pop() ?? path
  const index = name.lastIndexOf(".")
  return index === -1 ? name : name.slice(0, index)
}

export function joinPath(dir: string, name: string): string {
  return dir ? `${dir}/${name}` : name
}

export function roleValuesFromSimulation(simulation: Simulation): Partial<Record<FileRoleKey, string>> {
  const values: Partial<Record<FileRoleKey, string>> = {}
  for (const key of Object.keys({ ...simulation.files, ...simulation.resolved_files }) as FileRoleKey[]) {
    values[key] = simulation.resolved_files[key] ?? simulation.files[key] ?? ""
  }
  return values
}

/**
 * Presence of a role's file per the manifest's server-side check; null when the
 * manifest doesn't declare the role (absent is not "missing").
 */
export function rolePresence(simulation: Simulation, key: string): boolean | null {
  if (simulation.missing_files.includes(key)) return false
  if (!simulation.files[key]) return null
  return true
}

/**
 * Subset of `requiredRoles` whose files are absent for this simulation — the
 * availability predicate shared by the tune/analyze/publish wizards.
 */
export function missingRequiredRoles(simulation: Simulation, requiredRoles: readonly string[]): string[] {
  return requiredRoles.filter((role) => rolePresence(simulation, role) !== true)
}
