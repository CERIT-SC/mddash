import type { Simulation } from "@/api/generated/models"

export function simulation(path: string, overrides: Partial<Simulation> = {}): Simulation {
  return {
    simulation_path: path,
    name: `Simulation ${path}`,
    engine: "GMX",
    files: {},
    resolved_files: {},
    extra_args: "",
    locked: false,
    valid: false,
    errors: [],
    missing_files: [],
    step: 0,
    status: "setup",
    last_activity: 0,
    ...overrides,
  }
}
