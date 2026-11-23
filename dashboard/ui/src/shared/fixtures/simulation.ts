import { Step, type Simulation } from "@/api/generated/models"

export function simulation(path: string, overrides: Partial<Simulation> = {}): Simulation {
  return {
    simulation_path: path,
    name: `Simulation ${path}`,
    engine: "GMX",
    files: {},
    resolved_files: {},
    extra_args: "",
    default_resources: null,
    locked: false,
    valid: false,
    errors: [],
    missing_files: [],
    step: Step.setup,
    status: "setup",
    live: false,
    last_activity: 0,
    ...overrides,
  }
}
