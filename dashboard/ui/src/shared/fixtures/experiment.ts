import { Step, type Experiment, type PodStatus, type Population, type PopulationPhase } from "@/api/generated/models"

export function experiment(id: string, overrides: Partial<Experiment> = {}): Experiment {
  return {
    id,
    name: `Experiment ${id}`,
    created_at: "2026-08-13T00:00:00Z",
    updated_at: new Date(Date.now() - 12 * 60_000).toISOString(),
    source: null,
    engine: "GMX",
    latest_simulation_path: null,
    notebook: null,
    population: null,
    tuner_jobs: [],
    simulation_jobs: [],
    analysis_jobs: [],
    step: Step.configuration,
    status: "setup complete",
    archived_at: null,
    archive_state: null,
    ...overrides,
  }
}

export function withPopulation(
  experimentId: string,
  population: Partial<Population> & Pick<Population, "status">
): Population {
  return {
    operation_id: `op-${experimentId}`,
    experiment_id: experimentId,
    phase: "starting" satisfies PopulationPhase,
    files_present: 0,
    files_total: null,
    bytes_present: 0,
    bytes_total: null,
    byte_percentage: null,
    error: null,
    ...population,
  }
}

export function withNotebook(status: PodStatus, experimentId = "exp1"): Experiment["notebook"] {
  return {
    id: 1,
    experiment_id: experimentId,
    token: "t",
    gpu: false,
    path: `/${experimentId}`,
    status,
    started_at: status === "RUNNING" ? new Date(Date.now() - 5 * 60_000).toISOString() : null,
  }
}
