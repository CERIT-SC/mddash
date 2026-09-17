import type { AnalysisJob, SimulationJob } from "@/api/generated/models"
import { experiment, withNotebook } from "@/shared/fixtures/experiment"
import { mockApiBySuffix, requestUrl } from "@/shared/fixtures/mock-fetch"
import { EXPERIMENTS_URL, NOTEBOOK_CONFIG_URL, notebookConfigResponse } from "@/shared/fixtures/notebook-quota"
import { renderWithProviders } from "@/shared/fixtures/render-with-providers"
import { act, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { Dashboard, type DashboardSearch } from "./dashboard"

afterEach(() => {
  vi.useRealTimers()
})

function renderDashboard(search: DashboardSearch = {}) {
  return renderWithProviders(<Dashboard search={search} onSearchChange={() => undefined} />)
}

function simulationJob(status: SimulationJob["status"], overrides: Partial<SimulationJob> = {}): SimulationJob {
  return {
    id: "s1",
    experiment_id: "one",
    simulation_path: "md.simulation.json",
    created_at: "2026-08-13T00:00:00Z",
    engine: "GMX",
    np: 4,
    ntomp: 2,
    status,
    is_live: status === "RUNNING" || status === "PENDING",
    ...overrides,
  }
}

function analysisJob(status: AnalysisJob["status"]): AnalysisJob {
  return {
    id: "a1",
    experiment_id: "one",
    simulation_path: "md.simulation.json",
    analysis_name: "clusters",
    created_at: "2026-08-13T00:00:00Z",
    status,
  }
}

describe("Dashboard", () => {
  it("groups experiments by notebook state with counts against the concurrent limit", async () => {
    mockApiBySuffix({
      [EXPERIMENTS_URL]: Response.json([
        experiment("one", { notebook: withNotebook("RUNNING") }),
        experiment("two", { notebook: withNotebook("DOWN") }),
        experiment("three"),
      ]),
      [NOTEBOOK_CONFIG_URL]: notebookConfigResponse(2),
    })
    await renderDashboard()
    const running = await screen.findByRole("heading", { name: /notebook running/i })
    expect(within(running).getByText("1/2")).toBeVisible()
    const stopped = screen.getByRole("heading", { name: /notebook stopped/i })
    expect(within(stopped).getByText("2")).toBeVisible()
    expect(screen.getByText("Experiment one")).toBeVisible()
    expect(screen.getByText("Experiment three")).toBeVisible()
  })

  it("falls back to a plain running count while the limit is unavailable", async () => {
    mockApiBySuffix({
      [EXPERIMENTS_URL]: Response.json([experiment("one", { notebook: withNotebook("RUNNING") })]),
      [NOTEBOOK_CONFIG_URL]: new Response(null, { status: 404 }),
    })
    await renderDashboard()
    const running = await screen.findByRole("heading", { name: /notebook running/i })
    expect(within(running).getByText("1")).toBeVisible()
    expect(within(running).queryByText(/\/2/)).not.toBeInTheDocument()
  })

  it("filters experiments by search query", async () => {
    mockApiBySuffix({
      [EXPERIMENTS_URL]: Response.json([
        experiment("alpha", { name: "Analyze protein" }),
        experiment("beta", { name: "Tuning membrane" }),
      ]),
      [NOTEBOOK_CONFIG_URL]: notebookConfigResponse(),
    })
    await renderDashboard({ q: "membrane" })
    expect(await screen.findByText("Tuning membrane")).toBeVisible()
    expect(screen.queryByText("Analyze protein")).not.toBeInTheDocument()
  })

  it("shows a create card as the empty state when there are no experiments", async () => {
    mockApiBySuffix({ [EXPERIMENTS_URL]: Response.json([]), [NOTEBOOK_CONFIG_URL]: notebookConfigResponse() })
    await renderDashboard()
    const create = await screen.findByRole("link", { name: /create your first experiment/i })
    expect(create).toHaveAttribute("href", "/new")
    expect(within(create).getByText("Set up a molecular dynamics run")).toBeVisible()
  })

  it("shows a no-match state when the search filters everything out", async () => {
    mockApiBySuffix({
      [EXPERIMENTS_URL]: Response.json([experiment("alpha", { name: "Analyze" })]),
      [NOTEBOOK_CONFIG_URL]: notebookConfigResponse(),
    })
    await renderDashboard({ q: "zzz" })
    expect(await screen.findByText("No experiments match “zzz”.")).toBeVisible()
  })

  it("shows problem details and retries a failed response", async () => {
    let experimentsCalls = 0
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      const url = requestUrl(input)
      if (url.endsWith(EXPERIMENTS_URL)) {
        experimentsCalls += 1
        return experimentsCalls === 1
          ? Response.json(
              { type: "urn:mddash:upstream-unavailable", title: "Unavailable", detail: "Try later" },
              { status: 503 }
            )
          : Response.json([experiment("recovered")])
      }
      return new Response(null, { status: 404 })
    })
    const user = userEvent.setup()
    await renderDashboard()
    expect(await screen.findByRole("alert")).toHaveTextContent("urn:mddash:upstream-unavailable")
    await user.click(screen.getByRole("button", { name: "Retry" }))
    expect(await screen.findByText("Experiment recovered")).toBeVisible()
  })

  it("disables unimplemented features", async () => {
    mockApiBySuffix({
      [EXPERIMENTS_URL]: Response.json([experiment("one")]),
      [NOTEBOOK_CONFIG_URL]: notebookConfigResponse(),
    })
    await renderDashboard()
    expect(await screen.findByRole("link", { name: /new/i })).toBeVisible()
    expect(screen.getByRole("tab", { name: /archived/i })).toBeDisabled()
  })

  it("writes live job progress through to the cards while work runs", async () => {
    vi.useFakeTimers()
    const state = { status: "RUNNING" as SimulationJob["status"], nsteps_done: 40 }
    let listCalls = 0
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      const url = requestUrl(input)
      if (url.endsWith(EXPERIMENTS_URL)) {
        listCalls += 1
        return Response.json([
          experiment("one", {
            name: "Analyze",
            step: 2,
            status: "simulating",
            simulation_jobs: [simulationJob(state.status, { nsteps: 100, nsteps_done: state.nsteps_done })],
          }),
        ])
      }
      if (url.endsWith(NOTEBOOK_CONFIG_URL)) return notebookConfigResponse(2)
      return new Response(null, { status: 404 })
    })
    await renderDashboard()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })
    expect(screen.getByText("Simulating · 40%")).toBeVisible()

    state.nsteps_done = 80
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000)
    })
    expect(screen.getByText("Simulating · 80%")).toBeVisible()

    // The list settles with the job and polling stops with it.
    state.status = "FINISHED"
    state.nsteps_done = 100
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000)
    })
    expect(screen.getByText("Active 12 min ago")).toBeVisible()
    const settledCalls = listCalls
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })
    expect(listCalls).toBe(settledCalls)
  })

  it("refreshes analysis counts on the cards when a running analysis settles", async () => {
    vi.useFakeTimers()
    const state = { analysisStatus: "RUNNING" as AnalysisJob["status"] }
    const resultsCalls: string[] = []
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      const url = requestUrl(input)
      if (url.endsWith(EXPERIMENTS_URL)) {
        return Response.json([
          experiment("one", {
            name: "Analyze",
            step: 3,
            status: "analyzing",
            latest_simulation_path: "md.simulation.json",
            simulation_jobs: [simulationJob("FINISHED")],
            analysis_jobs: [analysisJob(state.analysisStatus)],
          }),
        ])
      }
      if (url.endsWith(NOTEBOOK_CONFIG_URL)) return notebookConfigResponse(2)
      if (url.includes("/analysis/results")) {
        resultsCalls.push(url)
        // Results land only once the calculation finishes.
        return Response.json(state.analysisStatus === "RUNNING" ? [] : ["clusters"])
      }
      if (url.includes("/analysis/types")) {
        return Response.json(["rmsds", "clusters", "sas", "hbonds"])
      }
      return new Response(null, { status: 404 })
    })
    await renderDashboard()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })
    expect(screen.getByText("Analyzing Clusters")).toBeVisible()
    expect(screen.getByText("0 of 4 ready")).toBeVisible()

    state.analysisStatus = "FINISHED"
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000)
    })
    expect(screen.getByText("1 of 4 ready")).toBeVisible()
    // The settle edge refetches the result list so the Models row counts it.
    expect(resultsCalls).toHaveLength(2)
    const modelsRow = screen.getByText("Models").closest("div")
    expect(modelsRow).not.toBeNull()
    expect(within(modelsRow as HTMLElement).getByText("1")).toBeVisible()
  })
})
