import type { Experiment, PodStatus } from "@/api/generated/models"

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
    tuner_jobs: [],
    simulation_jobs: [],
    analysis_jobs: [],
    step: 1,
    status: "setup complete",
    ...overrides,
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
