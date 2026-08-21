import type { AmberJob, GromacsJob, TunerJob, TunerTrial } from "@/api/generated/models"
import type { FetchCall } from "@/shared/fixtures/mock-fetch"
import { requestUrl } from "@/shared/fixtures/mock-fetch"
import { simulation } from "@/shared/fixtures/simulation"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { RunStep } from "./run-step"

const SIM = "md.simulation.json"
const GMX_ONE = `/experiments/exp1/gmx/${SIM}`
const AMBER_ONE = `/experiments/exp1/amber/${SIM}`
const TUNER_ONE = `/experiments/exp1/tuner/${SIM}`

const FAST_TRIAL: TunerTrial = {
  id: "t1",
  status: "FINISHED",
  performance: 704.12,
  estimated_time: 0.15,
  estimated_cost: 2.6,
  np: 1,
  ntomp: 1,
  pme: "cpu",
  nb: "cpu",
}
const ECO_TRIAL: TunerTrial = {
  id: "t2",
  status: "FINISHED",
  performance: 41.27,
  estimated_time: 2.68,
  estimated_cost: 1.2,
  np: 1,
  ntomp: 2,
  pme: "gpu",
  nb: "gpu",
}

function gmxJob(overrides: Partial<GromacsJob> = {}): GromacsJob {
  return {
    id: "job1",
    experiment_id: "exp1",
    simulation_path: SIM,
    created_at: "2026-08-19T00:00:00Z",
    engine: "GMX",
    np: 1,
    ntomp: 1,
    pme: "cpu",
    nb: "cpu",
    status: "RUNNING",
    start_timestamp: 1_755_000_000,
    finish_timestamp: null,
    nsteps: 10000,
    nsteps_done: 2000,
    performance: null,
    estimated_time: 142,
    log_lines: { gmx: 1482, stdout: 318, stderr: 0 },
    ...overrides,
  }
}

function tunerJob(trials: TunerTrial[]): TunerJob {
  return {
    id: "tune1",
    experiment_id: "exp1",
    simulation_path: SIM,
    nsteps: 25000,
    created_at: "2026-08-19T00:00:00Z",
    is_stopped: false,
    engine: "GMX",
    tuner_status: "FINISHED",
    sim_length_ns: 100,
    trials,
  }
}

type MockRunOptions = {
  /** undefined = default running job; null = no job (404). */
  initial?: GromacsJob | AmberJob | null
  trials?: TunerTrial[]
  logs?: Record<string, string>
}

function mockRun(options: MockRunOptions = {}) {
  const state = { job: options.initial === undefined ? gmxJob() : options.initial }
  const logs = options.logs ?? {
    gmx: "gmx log contents\n",
    mdout: "mdout log contents\n",
    stdout: "stdout contents\n",
    stderr: "",
  }
  const trials = options.trials ?? []
  const calls: FetchCall[] = []
  vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input)
    const method = init?.method ?? "GET"
    calls.push({
      url,
      method,
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
    })
    for (const one of [GMX_ONE, AMBER_ONE]) {
      if (url.includes(`${one}/log`)) {
        const type = new URL(url, "http://test").searchParams.get("type") ?? (one === AMBER_ONE ? "mdout" : "gmx")
        const text = logs[type]
        return text === undefined ? new Response(null, { status: 404 }) : Response.json(text)
      }
      if (url.endsWith(one)) {
        if (method === "DELETE") {
          state.job = null
          return new Response(null, { status: 204 })
        }
        if (method === "POST") {
          const body = (typeof init?.body === "string" ? JSON.parse(init.body) : {}) as Partial<GromacsJob>
          state.job = gmxJob({ ...body, id: "job2", status: "RUNNING" }) as GromacsJob | AmberJob
          return Response.json(state.job, { status: 201 })
        }
        return state.job === null ? new Response(null, { status: 404 }) : Response.json(state.job)
      }
    }
    if (url.endsWith(TUNER_ONE)) {
      return trials.length === 0 ? new Response(null, { status: 404 }) : Response.json(tunerJob(trials))
    }
    if (url.endsWith("/experiments/exp1") || url.endsWith("/experiments/exp1/simulations")) return Response.json({})
    return new Response(null, { status: 404 })
  })
  return { state, calls }
}

function renderRun(props: Partial<React.ComponentProps<typeof RunStep>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const spies = { onStepChange: props.onStepChange ?? vi.fn() }
  render(
    <QueryClientProvider client={client}>
      <RunStep
        experimentId="exp1"
        engine="GMX"
        simulation={simulation(SIM, { valid: true, missing_files: [] })}
        {...spies}
        {...props}
      />
    </QueryClientProvider>
  )
  return spies
}

afterEach(() => vi.unstubAllGlobals())

describe("RunStep pending job", () => {
  it("shows Preparing without step counts or estimates", async () => {
    mockRun({
      initial: gmxJob({
        status: "PENDING",
        start_timestamp: null,
        nsteps: null,
        nsteps_done: null,
        estimated_time: null,
        log_lines: { gmx: null, stdout: null, stderr: null },
      }),
    })
    renderRun()

    expect(await screen.findByText("Run your simulation")).toBeInTheDocument()
    expect(await screen.findByText("Preparing")).toBeInTheDocument()
    expect(screen.getByRole("progressbar")).toBeInTheDocument()
    expect(screen.queryByText(/steps$/)).not.toBeInTheDocument()
    expect(screen.queryByText(/remaining/)).not.toBeInTheDocument()
    // The job's hardware config is shown; estimates stay dashed without a tuner match.
    expect(screen.getAllByText("CPU")).not.toHaveLength(0)
    expect(screen.getAllByText("—")).toHaveLength(3)
    expect(screen.getByRole("button", { name: /stop run/i })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /analyze/i })).toBeDisabled()
  })
})

describe("RunStep running job", () => {
  it("shows percentage, step counts, and remaining time", async () => {
    mockRun()
    renderRun()

    expect(await screen.findByText("20%")).toBeInTheDocument()
    expect(screen.getByText("2,000 / 10,000 steps")).toBeInTheDocument()
    expect(screen.getByText("About 2m 22s remaining")).toBeInTheDocument()
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "20")
  })

  it("advances progress while polling", async () => {
    const { state } = mockRun()
    renderRun({ pollMs: 25 })

    await screen.findByText("20%")
    state.job = gmxJob({ nsteps_done: 5000, estimated_time: 80 })
    expect(await screen.findByText("50%")).toBeInTheDocument()
  })

  it("shows estimates and badges from the tuner trial matching the job config", async () => {
    const rerunOfSameConfig: TunerTrial = { ...FAST_TRIAL, id: "t1b", status: "RUNNING", performance: null }
    mockRun({ trials: [rerunOfSameConfig, FAST_TRIAL, ECO_TRIAL] })
    renderRun()

    expect(await screen.findByText("Fastest")).toBeInTheDocument()
    expect(screen.queryByText("Eco")).not.toBeInTheDocument()
    expect(screen.getByText("704.12")).toBeInTheDocument()
    expect(screen.getByText("9m")).toBeInTheDocument()
    expect(screen.getByText("$2.6")).toBeInTheDocument()
    expect(screen.queryAllByText("—")).toHaveLength(0)
  })

  it("shows dashed estimates when no trial matches a manual config", async () => {
    mockRun({ trials: [ECO_TRIAL] })
    renderRun()

    expect(await screen.findByText("20%")).toBeInTheDocument()
    expect(screen.queryByText("Fastest")).not.toBeInTheDocument()
    expect(screen.getAllByText("—")).toHaveLength(3)
  })
})

describe("RunStep finished job", () => {
  it("shows Finished, enables Analyze, and hides the stop button", async () => {
    mockRun({ initial: gmxJob({ status: "FINISHED", nsteps_done: 10000, estimated_time: 0, performance: 62.5 }) })
    const spies = renderRun()

    expect(await screen.findByText("Finished")).toBeInTheDocument()
    expect(screen.getByText("10,000 / 10,000 steps")).toBeInTheDocument()
    expect(screen.queryByText(/remaining/)).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: /re-run/i })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /stop run/i })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: /analyze/i }))
    expect(spies.onStepChange).toHaveBeenCalledWith(3)
  })

  it("re-runs with the job's config after confirmation", async () => {
    const { calls } = mockRun({ initial: gmxJob({ status: "FINISHED", nsteps_done: 10000 }) })
    const spies = renderRun()

    await userEvent.click(await screen.findByRole("button", { name: /re-run/i }))
    const dialog = await screen.findByRole("alertdialog")
    await userEvent.click(within(dialog).getByRole("button", { name: /re-run/i }))

    await waitFor(() => {
      const deleteIndex = calls.findIndex((call) => call.method === "DELETE" && call.url.endsWith(GMX_ONE))
      const post = calls.find((call) => call.method === "POST" && call.url.endsWith(GMX_ONE))
      expect(deleteIndex).toBeGreaterThanOrEqual(0)
      expect(post?.body).toEqual({ np: 1, ntomp: 1, pme: "cpu", nb: "cpu" })
      expect(calls.findIndex((call) => call.method === "POST")).toBeGreaterThan(deleteIndex)
    })
    // The re-submit chain must not trip the gone-job auto-navigation.
    expect(spies.onStepChange).not.toHaveBeenCalled()
  })
})

describe("RunStep error job", () => {
  it("shows Failed and opens the logs on standard error", async () => {
    const { calls } = mockRun({ initial: gmxJob({ status: "ERROR" }), logs: { stderr: "simulation exploded\n" } })
    renderRun()

    expect(await screen.findByText("Failed")).toBeInTheDocument()
    expect(await screen.findByText("simulation exploded")).toBeInTheDocument()
    expect(calls.some((call) => call.url.includes("type=stderr"))).toBe(true)
  })
})

describe("RunStep stop flow", () => {
  it("deletes the job after confirmation and navigates back to Tune", async () => {
    const { calls } = mockRun()
    const spies = renderRun({ pollMs: 25 })

    await userEvent.click(await screen.findByRole("button", { name: /stop run/i }))
    const dialog = await screen.findByRole("alertdialog")
    await userEvent.click(within(dialog).getByRole("button", { name: /stop run/i }))

    expect(calls.some((call) => call.method === "DELETE" && call.url.endsWith(GMX_ONE))).toBe(true)
    await waitFor(() => expect(spies.onStepChange).toHaveBeenCalledWith(1))
  })

  it("cancelling the stop dialog keeps the job", async () => {
    const { calls } = mockRun()
    renderRun()

    await userEvent.click(await screen.findByRole("button", { name: /stop run/i }))
    const dialog = await screen.findByRole("alertdialog")
    await userEvent.click(within(dialog).getByRole("button", { name: /keep running/i }))

    expect(calls.some((call) => call.method === "DELETE")).toBe(false)
    expect(await screen.findByText("20%")).toBeInTheDocument()
  })
})

describe("RunStep without a job", () => {
  it("navigates to Tune", async () => {
    mockRun({ initial: null })
    const spies = renderRun()

    await waitFor(() => expect(spies.onStepChange).toHaveBeenCalledWith(1))
  })
})

describe("RunStep logs", () => {
  it("sizes streams from the job payload and fetches only the open tab", async () => {
    const { calls } = mockRun()
    renderRun()

    // Counts ride the job payload — visible while collapsed, no log fetch yet.
    expect(await screen.findByText("1,800")).toBeInTheDocument()
    expect(calls.some((call) => call.url.includes("/log"))).toBe(false)

    await userEvent.click(screen.getByRole("button", { name: /logs/i }))
    expect(await screen.findByText("gmx log contents")).toBeInTheDocument()
    expect(calls.some((call) => call.url.includes("type=gmx"))).toBe(true)
    expect(calls.some((call) => call.url.includes("type=stdout"))).toBe(false)
    expect(screen.getByText("318")).toBeInTheDocument()
    expect(screen.getByText(/standard error/i).closest("[data-state]")).toBeInTheDocument()

    await userEvent.click(screen.getByRole("tab", { name: /standard error/i }))
    expect(calls.some((call) => call.url.includes("type=stderr"))).toBe(true)
    expect(await screen.findByText(/standard error is empty/i)).toBeInTheDocument()
  })

  it("does not flash a truncation note when the payload count is one poll ahead", async () => {
    // Live logs: the job poll counts a new line before the log refetch delivers it.
    const { calls } = mockRun({
      initial: gmxJob({ log_lines: { gmx: 450, stdout: 1, stderr: 0 } }),
      logs: { gmx: "line\n".repeat(449) },
    })
    renderRun()

    await userEvent.click(await screen.findByRole("button", { name: /logs/i }))
    await waitFor(() => expect(calls.some((call) => call.url.includes("type=gmx"))).toBe(true))
    // The pane renders only after the fetched text lands.
    await waitFor(() => expect(document.querySelector(".font-mono")).not.toBeNull())

    expect(screen.queryByText(/showing the last/i)).not.toBeInTheDocument()
  })

  it("notes the truncation only when the fetched window actually hit the tail cap", async () => {
    const capped = "line\n".repeat(10000)
    mockRun({
      initial: gmxJob({ log_lines: { gmx: 12000, stdout: 0, stderr: 0 } }),
      logs: { gmx: capped },
    })
    renderRun()

    await userEvent.click(await screen.findByRole("button", { name: /logs/i }))
    expect(await screen.findByText("Showing the last 10,000 of 12,000 lines")).toBeInTheDocument()
  })

  it("follows output, and copies/downloads scoped to the active tab", async () => {
    mockRun()
    renderRun()

    await userEvent.click(await screen.findByRole("button", { name: /logs/i }))
    expect(screen.getByRole("checkbox", { name: /follow output/i })).toBeChecked()

    // Stream actions sit on the selector row, named after the active tab.
    const selectorRow = screen.getByRole("tablist", { name: /log stream/i }).parentElement as HTMLElement
    expect(within(selectorRow).getByRole("button", { name: /copy gromacs log/i })).toBeInTheDocument()
    expect(within(selectorRow).getByRole("button", { name: /download gromacs log/i })).toBeInTheDocument()

    await userEvent.click(screen.getByRole("tab", { name: /standard output/i }))
    expect(within(selectorRow).getByRole("button", { name: /copy standard output/i })).toBeInTheDocument()
    expect(within(selectorRow).getByRole("button", { name: /download standard output/i })).toBeInTheDocument()
  })
})

describe("RunStep AMBER", () => {
  it("shows the engine config and mdout tab", async () => {
    mockRun({
      initial: {
        ...gmxJob(),
        engine: "AMBER",
        binary: "pmemd.cuda",
        ewald: "optimized",
        log_lines: { mdout: 41, stdout: 3, stderr: 0 },
      } as AmberJob,
    })
    renderRun({ engine: "AMBER" })

    expect(await screen.findByText("20%")).toBeInTheDocument()
    expect(screen.getByText("pmemd.cuda")).toBeInTheDocument()
    expect(screen.getByText("optimized")).toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: /logs/i }))
    expect(await screen.findByText("mdout log contents")).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: /amber log/i })).toBeInTheDocument()
  })
})
