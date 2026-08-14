import type { Experiment, PodStatus } from "@/api/generated/models"
import { vi } from "vitest"

export type FetchCall = { url: string; method: string; body?: unknown }

export function experiment(id: string, overrides: Partial<Experiment> = {}): Experiment {
  return {
    id,
    name: `Experiment ${id}`,
    created_at: "2026-08-13T00:00:00Z",
    updated_at: new Date(Date.now() - 12 * 60_000).toISOString(),
    source_message: null,
    engine: "GMX",
    latest_simulation_path: null,
    notebook: null,
    tuner_jobs: [],
    simulation_jobs: [],
    analysis_jobs: [],
    step: 2,
    status: "setup",
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
  }
}

export function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input
  return input instanceof URL ? input.href : input.url
}

export function mockFetch(...responses: Response[]): FetchCall[] {
  const queue = [...responses]
  const calls: FetchCall[] = []
  vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({
      url: requestUrl(input),
      method: init?.method ?? "GET",
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
    })
    return queue.shift() ?? new Response("[]", { status: 200 })
  })
  return calls
}
