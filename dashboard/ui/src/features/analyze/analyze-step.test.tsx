import type { AnalysisJob } from "@/api/generated/models"
import type { FetchCall } from "@/shared/fixtures/mock-fetch"
import { requestUrl } from "@/shared/fixtures/mock-fetch"
import { simulation } from "@/shared/fixtures/simulation"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AnalyzeStep } from "./analyze-step"

// Real renderers boot ECharts (needs canvas, absent in jsdom) — stub the
// registry and assert the panel passes it the right analysis name + payload.
const renderSpy = vi.fn<(props: { analysisName: string; data: unknown }) => void>()
vi.mock("./renderers", () => ({
  __esModule: true,
  AnalysisRenderer: (props: { analysisName: string; data: unknown }) => {
    renderSpy(props)
    return <div data-testid="analysis-renderer">{props.analysisName}</div>
  },
}))

// The trajectory tab is the default, so MolStar would mount — it needs WebGL,
// absent in jsdom. Stub it like the renderers.
vi.mock("./mol-star", () => ({
  __esModule: true,
  default: () => <div data-testid="mol-star" />,
}))

const SIM = "md.simulation.json"
const JOBS = `/experiments/exp1/analysis`
const RESULTS = `${JOBS}/results`
const GMX_JOB = `/experiments/exp1/gmx/${SIM}`

const READY_SIM = simulation(SIM, {
  valid: true,
  missing_files: [],
  files: { reference_structure: "ref.pdb", trajectory: "prod.xtc" },
  resolved_files: { reference_structure: "ref.pdb", trajectory: "prod.xtc" },
})

function job(overrides: Partial<AnalysisJob> = {}): AnalysisJob {
  return {
    id: "job1",
    experiment_id: "exp1",
    simulation_path: SIM,
    analysis_name: "rmsds",
    created_at: "2026-08-19T00:00:00Z",
    status: "RUNNING",
    ...overrides,
  }
}

const RUNNING_SIM_JOB = {
  id: "simjob1",
  experiment_id: "exp1",
  simulation_path: SIM,
  engine: "GMX",
  status: "RUNNING",
  np: 1,
  ntomp: 1,
  created_at: "2026-08-19T00:00:00Z",
  nsteps: 100,
  nsteps_done: 20,
}

const RMSDS_RESULT = {
  start: 0,
  step: 1,
  data: [{ reference: "ref", group: "protein", values: [0.1, 0.2, 0.4] }],
}

const DOWN_NOTEBOOK = {
  id: 1,
  experiment_id: "exp1",
  token: "tok",
  gpu: false,
  path: "/user/exp1/?token=tok",
  status: "DOWN",
  started_at: null,
}

const RUNNING_NOTEBOOK = { ...DOWN_NOTEBOOK, status: "RUNNING", started_at: "2026-08-19T00:00:00Z" }

const ANALYSIS_NOTEBOOK_FILE = { name: "analysis.ipynb", size: 10, path: "analysis.ipynb", url: "x" }

type MockAnalyzeOptions = {
  jobs?: AnalysisJob[]
  results?: string[]
  /** Payload per result name (for GET one result). */
  payloads?: Record<string, unknown>
  /** Gromacs job body; absent means a 404 (no run for this simulation). */
  simJob?: unknown
  /** Notebook body; absent means a 404 (notebook query unresolved). */
  notebook?: unknown
  /** Files list (GET files?ext=…). */
  files?: unknown[]
}

function mockAnalyze(options: MockAnalyzeOptions = {}) {
  const state = { jobs: options.jobs ?? [], results: options.results ?? [], payloads: options.payloads ?? {} }
  const calls: FetchCall[] = []

  vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input)
    const method = init?.method ?? "GET"
    calls.push({
      url,
      method,
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
    })

    if (url.includes("/variants")) {
      return url.includes(RESULTS) ? Response.json([]) : new Response(null, { status: 404 })
    }
    if (url.includes(`${RESULTS}/`)) {
      const name = url.slice(url.indexOf(`${RESULTS}/`) + `${RESULTS}/`.length).split("?")[0]
      const payload = state.payloads[name]
      return payload === undefined ? new Response(null, { status: 404 }) : Response.json(payload)
    }
    if (url.includes(RESULTS)) {
      return Response.json(state.results)
    }
    if (url.includes("/logs")) {
      return Response.json("analysis log output\n")
    }
    if (method === "DELETE" && url.includes(`${JOBS}/job1`)) {
      state.jobs = []
      return new Response(null, { status: 204 })
    }
    if (method === "POST" && url.includes(JOBS)) {
      const body = (typeof init?.body === "string" ? JSON.parse(init.body) : {}) as Partial<AnalysisJob>
      const created = job({ id: "job1", ...body, status: "RUNNING", created_at: new Date().toISOString() })
      state.jobs = [created]
      return Response.json(created, { status: 201 })
    }
    if (url.includes(JOBS)) {
      return Response.json(state.jobs)
    }
    if (url.includes(GMX_JOB)) {
      return options.simJob === undefined ? new Response(null, { status: 404 }) : Response.json(options.simJob)
    }
    if (url.includes("/notebook/config")) {
      return new Response(null, { status: 404 })
    }
    if (url.includes("/notebook")) {
      return options.notebook === undefined ? new Response(null, { status: 404 }) : Response.json(options.notebook)
    }
    if (url.includes("/files")) {
      return Response.json(options.files ?? [])
    }
    if (url.includes("/user/")) {
      // Notebook readiness probe hits the pod's own path, not the API.
      return new Response("ok", { status: 200 })
    }
    return new Response(null, { status: 404 })
  })

  return { state, calls }
}

function renderAnalyze(props: Partial<React.ComponentProps<typeof AnalyzeStep>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const spies = { onStepChange: props.onStepChange ?? vi.fn() }
  render(
    <QueryClientProvider client={client}>
      <AnalyzeStep experimentId="exp1" engine="GMX" simulation={READY_SIM} canPublish {...spies} {...props} />
    </QueryClientProvider>
  )
  return spies
}

/** The panel lives on the second tab; the trajectory viewer is the default. */
async function openAnalyzeTab() {
  await userEvent.click(await screen.findByRole("tab", { name: "Analyze" }))
}

beforeEach(() => renderSpy.mockClear())
afterEach(() => vi.unstubAllGlobals())

describe("AnalyzeStep layout", () => {
  it("renders the heading, tabs, and Back/Publish navigation", async () => {
    mockAnalyze()
    const spies = renderAnalyze()

    expect(await screen.findByText("Analyze the results")).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "View Trajectories" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Analyze" })).toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: /back/i }))
    expect(spies.onStepChange).toHaveBeenCalledWith(2)

    await userEvent.click(screen.getByRole("button", { name: /publish/i }))
    expect(spies.onStepChange).toHaveBeenCalledWith(4)
  })

  it("disables Publish while the step is still locked", async () => {
    mockAnalyze()
    renderAnalyze({ canPublish: false })

    expect(await screen.findByRole("button", { name: /publish/i })).toBeDisabled()
  })

  it("shows the still-running alert with progress while the simulation runs", async () => {
    mockAnalyze({ simJob: RUNNING_SIM_JOB })
    renderAnalyze()

    expect(await screen.findByText("Simulation is still running (20%)")).toBeInTheDocument()
    expect(screen.getByText("Results are still being calculated")).toBeInTheDocument()
  })

  it("always shows the notebook launcher so the notebook can be started from the step", async () => {
    mockAnalyze({ notebook: DOWN_NOTEBOOK })
    renderAnalyze()

    expect(await screen.findByRole("button", { name: /start notebook/i })).toBeInTheDocument()
    expect(screen.getByLabelText("Notebook launcher")).toBeInTheDocument()
  })

  it("deep-links Open notebook to the analysis notebook file", async () => {
    mockAnalyze({ notebook: RUNNING_NOTEBOOK, files: [ANALYSIS_NOTEBOOK_FILE] })
    renderAnalyze()

    const open = await screen.findByRole("link", { name: /open notebook/i })
    expect(open).toHaveAttribute("href", expect.stringContaining("lab/tree/analysis.ipynb?token=tok"))
  })
})

describe("AnalyzeStep empty state", () => {
  it("shows the picker prompt before any analysis is resolved", async () => {
    mockAnalyze()
    renderAnalyze()

    await openAnalyzeTab()
    expect(await screen.findByText("Select an analysis to view or calculate.")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /stop calculation/i })).not.toBeInTheDocument()
  })
})

describe("AnalyzeStep submit flow", () => {
  it("posts the chosen analysis and enters the running state", async () => {
    const { calls } = mockAnalyze()
    renderAnalyze()

    // Wait for the jobs query to resolve before the picker appears.
    await openAnalyzeTab()
    await screen.findByText("Select an analysis to view or calculate.")
    await userEvent.click(screen.getByRole("combobox", { name: /analysis/i }))
    await userEvent.click(await screen.findByRole("option", { name: /^RMSD/ }))

    await userEvent.click(screen.getByRole("button", { name: /calculate/i }))

    await waitFor(() => expect(calls.some((call) => call.method === "POST" && call.url.includes(JOBS))).toBe(true))
    const post = calls.find((call) => call.method === "POST" && call.url.includes(JOBS))
    expect(post?.body).toEqual({ simulation_path: SIM, analysis: "rmsds", preprocessing_mode: "as_is" })

    // The submitted job drives the running placeholder.
    expect(await screen.findByText("Results are being calculated…")).toBeInTheDocument()
  })
})

describe("AnalyzeStep running job", () => {
  it("shows the running state and cancels the job after confirmation", async () => {
    const { calls } = mockAnalyze({ jobs: [job()] })
    renderAnalyze()

    await openAnalyzeTab()
    expect(await screen.findByText("Results are being calculated…")).toBeInTheDocument()
    const runStatus = screen.getByRole("status")
    expect(runStatus).toHaveTextContent(/calculating rmsd/i)
    expect(runStatus.querySelector("strong")).toHaveTextContent("RMSD")
    await userEvent.click(screen.getByRole("button", { name: /stop calculation/i }))
    const dialog = await screen.findByRole("alertdialog")
    await userEvent.click(within(dialog).getByRole("button", { name: /cancel job/i }))

    expect(calls.some((call) => call.method === "DELETE" && call.url.includes(`${JOBS}/job1`))).toBe(true)
  })

  it("cancelling the dialog keeps the job running", async () => {
    const { calls } = mockAnalyze({ jobs: [job()] })
    renderAnalyze()

    await openAnalyzeTab()
    await userEvent.click(await screen.findByRole("button", { name: /stop calculation/i }))
    const dialog = await screen.findByRole("alertdialog")
    await userEvent.click(within(dialog).getByRole("button", { name: /keep running/i }))

    expect(calls.some((call) => call.method === "DELETE")).toBe(false)
    expect(await screen.findByText("Results are being calculated…")).toBeInTheDocument()
  })
})

describe("AnalyzeStep results", () => {
  it("renders the registry with the selected result and shows Re-calculate", async () => {
    mockAnalyze({ results: ["rmsds"], payloads: { rmsds: RMSDS_RESULT } })
    renderAnalyze()

    await openAnalyzeTab()
    expect(await screen.findByText("Re-calculate")).toBeInTheDocument()
    await waitFor(() => expect(renderSpy).toHaveBeenCalledWith({ analysisName: "rmsds", data: RMSDS_RESULT }))
    expect(await screen.findByTestId("analysis-renderer")).toBeInTheDocument()
  })

  it("refreshes results when a running job finishes", async () => {
    const { state } = mockAnalyze({ jobs: [job()], results: [], payloads: { rmsds: RMSDS_RESULT } })
    renderAnalyze({ pollMs: 50 })

    await openAnalyzeTab()
    expect(await screen.findByText("Results are being calculated…")).toBeInTheDocument()

    // The backend job completes: the next polls flip it to FINISHED and the
    // results list gains the payload — no manual reload needed.
    state.jobs = [job({ status: "FINISHED" })]
    state.results = ["rmsds"]

    await waitFor(() => expect(renderSpy).toHaveBeenCalledWith({ analysisName: "rmsds", data: RMSDS_RESULT }), {
      timeout: 5000,
    })
  })

  it("flags results calculated on a partial trajectory", async () => {
    mockAnalyze({
      jobs: [job({ status: "FINISHED", sim_progress: 0.2 })],
      results: ["rmsds"],
      payloads: { rmsds: RMSDS_RESULT },
    })
    renderAnalyze()

    await openAnalyzeTab()
    expect(await screen.findByText("Calculated at 20%")).toBeInTheDocument()
    expect(await screen.findByText("Re-calculate")).toBeInTheDocument()
  })

  it("omits the partial-result flag once the trajectory is complete", async () => {
    mockAnalyze({
      jobs: [job({ status: "FINISHED", sim_progress: 1 })],
      results: ["rmsds"],
      payloads: { rmsds: RMSDS_RESULT },
    })
    renderAnalyze()

    await openAnalyzeTab()
    expect(await screen.findByText("Re-calculate")).toBeInTheDocument()
    expect(screen.queryByText(/Calculated at/)).not.toBeInTheDocument()
  })
})

describe("AnalyzeStep analysis switching", () => {
  it("never renders a stale variant after switching to a non-variant analysis", async () => {
    const CLUSTERS_00_RESULT = { clusters: [{ index: 0, frames: [1, 2] }] }
    mockAnalyze({
      results: ["rmsds", "clusters-00"],
      payloads: { rmsds: RMSDS_RESULT, "clusters-00": CLUSTERS_00_RESULT },
    })
    renderAnalyze()

    await openAnalyzeTab()
    await waitFor(() => expect(renderSpy).toHaveBeenCalledWith({ analysisName: "rmsds", data: RMSDS_RESULT }))

    // Switch to Clusters (has variants): clusters-00 auto-selects and renders.
    await userEvent.click(screen.getByRole("combobox", { name: /analysis/i }))
    await userEvent.click(await screen.findByRole("option", { name: /^Clusters/ }))
    await waitFor(() =>
      expect(renderSpy).toHaveBeenCalledWith({ analysisName: "clusters-00", data: CLUSTERS_00_RESULT })
    )

    // Switch back to RMSD: from here on, no render may name clusters-00 —
    // a stale variant would briefly show the previous analysis under the RMSD
    // label (and the data is cached, so there is no loading gap to hide it).
    renderSpy.mockClear()
    await userEvent.click(screen.getByRole("combobox", { name: /analysis/i }))
    await userEvent.click(await screen.findByRole("option", { name: /^RMSD/ }))

    await waitFor(() => expect(renderSpy).toHaveBeenCalledWith({ analysisName: "rmsds", data: RMSDS_RESULT }))
    expect(renderSpy.mock.calls.every(([props]) => props.analysisName !== "clusters-00")).toBe(true)
  })
})

describe("AnalyzeStep failed job", () => {
  it("shows the failure placeholder and fetches logs on demand", async () => {
    mockAnalyze({ jobs: [job({ status: "ERROR" })] })
    renderAnalyze()

    // The picker loads first; selecting the analysis reveals its failed run.
    await openAnalyzeTab()
    await screen.findByText("Select an analysis to view or calculate.")
    await userEvent.click(screen.getByRole("combobox", { name: /analysis/i }))
    await userEvent.click(await screen.findByRole("option", { name: /^RMSD/ }))

    expect(await screen.findByText("Previous analysis run failed.")).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: /view logs/i }))
    expect(await screen.findByText(/analysis log output/)).toBeInTheDocument()
  })
})
