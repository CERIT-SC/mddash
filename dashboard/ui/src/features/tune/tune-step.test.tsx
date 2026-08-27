import type { TunerJob, TunerTrial } from "@/api/generated/models"
import { requestUrl } from "@/shared/fixtures/mock-fetch"
import { simulation } from "@/shared/fixtures/simulation"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { TuneStep } from "./tune-step"

const SIM = "md.simulation.json"
const TUNER_ONE = `/experiments/exp1/tuner/${SIM}`
const TUNER_ALL = "/experiments/exp1/tuner"
const GMX_ONE = `/experiments/exp1/gmx/${SIM}`

const FAST_TRIAL: TunerTrial = {
  id: "t1",
  status: "FINISHED",
  performance: 704.12,
  estimated_time: 0.15,
  estimated_cost: 2.6,
  np: 1,
  ntomp: 2,
  pme: "gpu",
  nb: "gpu",
}
const ECO_TRIAL: TunerTrial = {
  id: "t2",
  status: "FINISHED",
  performance: 41.27,
  estimated_time: 2.68,
  estimated_cost: 1.2,
  np: 1,
  ntomp: 1,
  pme: "cpu",
  nb: "cpu",
}
const RUNNING_TRIAL: TunerTrial = {
  id: "t3",
  status: "RUNNING",
  performance: null,
  np: 1,
  ntomp: 1,
  pme: "cpu",
  nb: "gpu",
}
const ERROR_TRIAL: TunerTrial = {
  id: "err1",
  status: "ERROR",
  performance: null,
  np: 1,
  ntomp: 1,
  pme: "cpu",
  nb: "cpu",
}

function tunerJob(overrides: Partial<TunerJob> = {}): TunerJob {
  return {
    id: "job1",
    experiment_id: "exp1",
    simulation_path: SIM,
    nsteps: 25000,
    created_at: "2026-08-19T00:00:00Z",
    is_stopped: false,
    engine: "GMX",
    tuner_status: "RUNNING",
    is_live: true,
    sim_length_ns: 100,
    trials: [],
    ...overrides,
  }
}

function mockTuner(initial: TunerJob | null, options: { submitFails?: boolean } = {}) {
  const state = { current: initial }
  const calls: { url: string; method: string; body?: unknown }[] = []
  vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input)
    const method = init?.method ?? "GET"
    calls.push({
      url,
      method,
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
    })
    if (url.endsWith(GMX_ONE) && method === "POST") {
      if (options.submitFails) {
        return Response.json(
          { type: "urn:mddash:forbidden", title: "Forbidden", detail: "MDRun refused the job." },
          { status: 403 }
        )
      }
      return Response.json({ id: "run1" }, { status: 201 })
    }
    if (url.endsWith(`${TUNER_ONE}/trials/err1/stdout`)) return Response.json("trial stdout contents")
    if (url.endsWith(`${TUNER_ONE}/trials/err1/stderr`)) return Response.json("trial stderr contents")
    if (url.endsWith(`${TUNER_ONE}/stop`)) return new Response(null, { status: 204 })
    if (url.endsWith(TUNER_ONE)) {
      if (method === "DELETE") {
        state.current = null
        return new Response(null, { status: 204 })
      }
      return state.current === null ? new Response(null, { status: 404 }) : Response.json(state.current)
    }
    if (url.endsWith(TUNER_ALL) && method === "POST") {
      const body = (typeof init?.body === "string" ? JSON.parse(init.body) : {}) as { nsteps: number }
      state.current = tunerJob({ nsteps: body.nsteps })
      return Response.json(state.current, { status: 201 })
    }
    if (url.endsWith("/experiments/exp1") || url.endsWith("/experiments/exp1/simulations")) return Response.json({})
    return new Response(null, { status: 404 })
  })
  return { state, calls }
}

function renderTune(props: Partial<React.ComponentProps<typeof TuneStep>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const spies = {
    onTrialIdChange: props.onTrialIdChange ?? vi.fn(),
    onModeChange: props.onModeChange ?? vi.fn(),
    onStepChange: props.onStepChange ?? vi.fn(),
  }
  render(
    <QueryClientProvider client={client}>
      <TuneStep
        experimentId="exp1"
        engine="GMX"
        simulation={simulation(SIM, {
          valid: true,
          missing_files: [],
          files: { run_input: "prod.tpr", reference_structure: "ref.gro", trajectory: "prod.xtc" },
        })}
        trialId={undefined}
        mode="tuning"
        {...spies}
        {...props}
      />
    </QueryClientProvider>
  )
  return spies
}

afterEach(() => vi.unstubAllGlobals())

describe("TuneStep idle state", () => {
  it("starts tuning with the default 25,000 steps after confirmation", async () => {
    const { calls } = mockTuner(null)
    renderTune()

    const start = await screen.findByRole("button", { name: /start tuning/i })
    expect(screen.getByText("25,000")).toBeInTheDocument()
    await userEvent.click(start)

    const dialog = await screen.findByRole("alertdialog")
    expect(dialog).toHaveTextContent("Start tuning with 25,000 steps?")
    expect(calls.some((call) => call.method === "POST")).toBe(false)

    await userEvent.click(within(dialog).getByRole("button", { name: /start tuning/i }))
    expect(calls.find((call) => call.method === "POST" && call.url.endsWith(TUNER_ALL))?.body).toEqual({
      simulation_path: SIM,
      nsteps: 25000,
    })
    expect(await screen.findByRole("button", { name: /stop tuning/i })).toBeInTheDocument()
  })

  it("cancelling the start dialog leaves the idle state untouched", async () => {
    const { calls } = mockTuner(null)
    renderTune()

    await userEvent.click(await screen.findByRole("button", { name: /start tuning/i }))
    const dialog = await screen.findByRole("alertdialog")
    await userEvent.click(within(dialog).getByRole("button", { name: /cancel/i }))

    expect(calls.some((call) => call.method === "POST")).toBe(false)
    expect(await screen.findByRole("button", { name: /start tuning/i })).toBeInTheDocument()
  })

  it("blocks tuning when the manifest is not setup-complete", async () => {
    mockTuner(null)
    renderTune({ simulation: simulation(SIM, { valid: false, missing_files: ["prod/topology.tpr"] }) })

    expect(await screen.findByText("Finish setup first")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /start tuning/i })).toBeDisabled()
  })

  it("allows re-tuning when only run-output roles (e.g. trajectory) are missing", async () => {
    mockTuner(null)
    renderTune({
      simulation: simulation(SIM, {
        valid: true,
        missing_files: ["trajectory", "run_structure"],
        files: { run_input: "prod.tpr", reference_structure: "ref.gro", trajectory: "prod.xtc" },
      }),
    })

    expect(await screen.findByRole("button", { name: /start tuning/i })).toBeEnabled()
    expect(screen.queryByText("Finish setup first")).not.toBeInTheDocument()
  })

  it("blocks tuning when a tuning-required role file is missing (GMX run input)", async () => {
    mockTuner(null)
    renderTune({
      simulation: simulation(SIM, {
        valid: true,
        missing_files: ["run_input"],
        files: { run_input: "prod.tpr", reference_structure: "ref.gro", trajectory: "prod.xtc" },
      }),
    })

    expect(await screen.findByText("Finish setup first")).toBeInTheDocument()
    expect(screen.getByText(/Run input/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /start tuning/i })).toBeDisabled()
  })

  it("blocks tuning when an AMBER input role file is missing", async () => {
    mockTuner(null)
    renderTune({
      engine: "AMBER",
      simulation: simulation(SIM, {
        engine: "AMBER",
        valid: true,
        files: { topology: "sys.prmtop", coordinates: "sys.inpcrd", control: "prod.mdin", trajectory: "prod.nc" },
        missing_files: ["topology"],
      }),
    })

    expect(await screen.findByText("Finish setup first")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /start tuning/i })).toBeDisabled()
  })

  it("allows AMBER tuning when only the trajectory output is missing", async () => {
    mockTuner(null)
    renderTune({
      engine: "AMBER",
      simulation: simulation(SIM, {
        engine: "AMBER",
        valid: true,
        files: { topology: "sys.prmtop", coordinates: "sys.inpcrd", control: "prod.mdin", trajectory: "prod.nc" },
        missing_files: ["trajectory"],
      }),
    })

    expect(await screen.findByRole("button", { name: /start tuning/i })).toBeEnabled()
    expect(screen.queryByText("Finish setup first")).not.toBeInTheDocument()
  })

  it("clears a carried-over pick and keeps Run disabled on a simulation with no tuner job", async () => {
    // Regression: a cross-tab pick survived on a job-less simulation and enabled Run.
    mockTuner(null)
    const spies = renderTune({ trialId: "t1" })

    await screen.findByRole("button", { name: /start tuning/i })
    expect(screen.getByRole("button", { name: /run simulation/i })).toBeDisabled()
    expect(spies.onTrialIdChange).toHaveBeenCalledWith(undefined)
  })
})

describe("TuneStep running job", () => {
  const job = tunerJob({ trials: [FAST_TRIAL, ECO_TRIAL, RUNNING_TRIAL] })

  it("renders suggestions, live rows, and enables picking", async () => {
    mockTuner(job)
    const spies = renderTune()

    expect(await screen.findByText("Fastest")).toBeInTheDocument()
    expect(screen.getByText("Eco")).toBeInTheDocument()
    expect(screen.getByText("704.12")).toBeInTheDocument()
    expect(screen.getByText("2h 40m")).toBeInTheDocument()
    expect(screen.getByText("$1.2")).toBeInTheDocument()
    expect(screen.getAllByRole("img", { name: "Running" })).not.toHaveLength(0)
    expect(screen.getByRole("radio", { name: "Pick configuration t3" })).toBeDisabled()

    expect(screen.getByRole("button", { name: /run simulation/i })).toBeDisabled()

    await userEvent.click(screen.getByRole("radio", { name: "Pick configuration t2" }))
    expect(spies.onTrialIdChange).toHaveBeenCalledWith("t2")
  })

  it("stops the job", async () => {
    const { calls } = mockTuner(job)
    renderTune()

    await userEvent.click(await screen.findByRole("button", { name: /stop tuning/i }))
    expect(calls.some((call) => call.method === "POST" && call.url.endsWith(`${TUNER_ONE}/stop`))).toBe(true)
  })

  it("enables Run Simulation once a trial is picked, submits the job, then navigates", async () => {
    const { calls } = mockTuner(job)
    const spies = renderTune({ trialId: "t2" })

    const run = screen.getByRole("button", { name: /run simulation/i })
    // The gate waits for the job load: the pick must exist in the job's trials.
    await waitFor(() => expect(run).toBeEnabled())
    await userEvent.click(run)
    expect(calls.find((call) => call.method === "POST" && call.url.endsWith(GMX_ONE))?.body).toEqual({
      np: 1,
      ntomp: 1,
      pme: "cpu",
      nb: "cpu",
    })
    expect(spies.onStepChange).toHaveBeenCalledWith(2)
  })

  it("stays on Tune when the run submission fails", async () => {
    const { calls } = mockTuner(job, { submitFails: true })
    const spies = renderTune({ trialId: "t2" })

    const run = screen.getByRole("button", { name: /run simulation/i })
    await waitFor(() => expect(run).toBeEnabled())
    await userEvent.click(run)

    await waitFor(() => expect(calls.some((call) => call.method === "POST" && call.url.endsWith(GMX_ONE))).toBe(true))
    expect(spies.onStepChange).not.toHaveBeenCalled()
  })
})

describe("TuneStep finished and error jobs", () => {
  it("clears a stale pick once the job settled", async () => {
    mockTuner(tunerJob({ is_stopped: true, is_live: false, tuner_status: "UNKNOWN", trials: [FAST_TRIAL] }))
    const spies = renderTune({ trialId: "gone" })

    await screen.findByText("Fastest")
    expect(spies.onTrialIdChange).toHaveBeenCalledWith(undefined)
    expect(screen.getByRole("button", { name: /re-tune/i })).toBeInTheDocument()
  })

  it("re-tunes a stopped job back to the idle state", async () => {
    // Regression: the 404'd refetch kept the deleted job as stale data, so idle never returned.
    const { calls } = mockTuner(
      tunerJob({ is_stopped: true, is_live: false, tuner_status: "UNKNOWN", trials: [FAST_TRIAL, ECO_TRIAL] })
    )
    const spies = renderTune({ trialId: "t1" })

    await userEvent.click(await screen.findByRole("button", { name: /re-tune/i }))
    const dialog = await screen.findByRole("alertdialog")
    await userEvent.click(within(dialog).getByRole("button", { name: "Re-tune" }))

    expect(calls.some((call) => call.method === "DELETE" && call.url.endsWith(TUNER_ONE))).toBe(true)
    expect(await screen.findByRole("button", { name: /start tuning/i })).toBeInTheDocument()
    expect(spies.onTrialIdChange).toHaveBeenCalledWith(undefined)
  })

  it("shows the tuner error and restarts via Tune again", async () => {
    const { calls } = mockTuner(
      tunerJob({ tuner_status: "ERROR", is_live: false, error_message: "The tuning service exploded." })
    )
    renderTune()

    expect(await screen.findByText("Tuning failed")).toBeInTheDocument()
    expect(screen.getByText("The tuning service exploded.")).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: /tune again/i }))

    const dialog = await screen.findByRole("alertdialog")
    expect(dialog).toHaveTextContent("Start tuning with 25,000 steps?")
    await userEvent.click(within(dialog).getByRole("button", { name: /start tuning/i }))
    expect(calls.find((call) => call.method === "POST" && call.url.endsWith(TUNER_ALL))?.body).toEqual({
      simulation_path: SIM,
      nsteps: 25000,
    })
  })
})

describe("TuneStep footer and manual tab", () => {
  it("goes back to Setup", async () => {
    mockTuner(null)
    const spies = renderTune()

    await userEvent.click(await screen.findByRole("button", { name: /back/i }))
    expect(spies.onStepChange).toHaveBeenCalledWith(0)
  })

  it("renders the manual form and reports tab switches", async () => {
    mockTuner(null)
    const spies = renderTune()

    await userEvent.click(screen.getByRole("tab", { name: /manual configuration/i }))
    expect(spies.onModeChange).toHaveBeenCalledWith("manual")
  })

  it("validates the manual form before Run Simulation submits", async () => {
    const { calls } = mockTuner(null)
    const spies = renderTune({ mode: "manual" })

    const run = await screen.findByRole("button", { name: /run simulation/i })
    expect(run).toBeDisabled()

    const [pmeSelect, nbSelect] = screen.getAllByRole("combobox")
    await userEvent.click(pmeSelect!)
    await userEvent.click(await screen.findByRole("option", { name: "GPU" }))
    await userEvent.click(nbSelect!)
    await userEvent.click(await screen.findByRole("option", { name: "GPU" }))
    await userEvent.type(screen.getByPlaceholderText("Enter number of ranks"), "1")
    await userEvent.type(screen.getByPlaceholderText("Enter number of threads"), "2")

    // Resolver validation is async — let it settle before asserting the gate lifts.
    await waitFor(() => expect(run).toBeEnabled())
    await userEvent.click(run)
    expect(calls.find((call) => call.method === "POST" && call.url.endsWith(GMX_ONE))?.body).toEqual({
      np: 1,
      ntomp: 2,
      pme: "gpu",
      nb: "gpu",
    })
    expect(spies.onStepChange).toHaveBeenCalledWith(2)
  })
})

describe("TuneStep degraded states", () => {
  it("warns when the tuner never answers and keeps the Stop exit available", async () => {
    mockTuner(tunerJob({ tuner_status: "UNKNOWN", trials: [] }))
    renderTune({ pollMs: 25 })

    expect(await screen.findByText("Waiting for the first trials…")).toBeInTheDocument()
    expect(await screen.findByText("The tuner is not responding", undefined, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /stop tuning/i })).toBeInTheDocument()
  })

  it("fetches each log stream only when its tab is shown", async () => {
    const { calls } = mockTuner(tunerJob({ trials: [ERROR_TRIAL] }))
    renderTune()

    await userEvent.click(await screen.findByRole("button", { name: /view output of failed trial err1/i }))
    expect(await screen.findByText("trial stdout contents")).toBeInTheDocument()
    expect(calls.some((call) => call.url.endsWith("/trials/err1/stdout"))).toBe(true)
    expect(calls.some((call) => call.url.endsWith("/trials/err1/stderr"))).toBe(false)

    await userEvent.click(screen.getByRole("tab", { name: /standard error/i }))
    expect(await screen.findByText("trial stderr contents")).toBeInTheDocument()
    expect(calls.some((call) => call.url.endsWith("/trials/err1/stderr"))).toBe(true)
  })
})

describe("TuneStep customize selected configuration", () => {
  const job = tunerJob({ trials: [FAST_TRIAL, ECO_TRIAL] })

  it("appears only after a trial is picked", async () => {
    mockTuner(job)
    renderTune()

    await screen.findByText("Fastest")
    expect(screen.queryByRole("button", { name: /customize selected configuration/i })).not.toBeInTheDocument()
  })

  it("pre-fills the picked trial's config and revalidates on edit", async () => {
    mockTuner(job)
    renderTune({ trialId: "t1" })

    await userEvent.click(await screen.findByRole("button", { name: /customize selected configuration/i }))
    // [0] is the disabled job-nsteps select; the hardware selects follow.
    const [, pmeSelect, nbSelect] = screen.getAllByRole("combobox")
    expect(pmeSelect).toHaveTextContent("GPU")
    expect(nbSelect).toHaveTextContent("GPU")
    expect(screen.getByPlaceholderText("Enter number of ranks")).toHaveValue(1)
    expect(screen.getByPlaceholderText("Enter number of threads")).toHaveValue(2)

    const run = screen.getByRole("button", { name: /run simulation/i })
    await waitFor(() => expect(run).toBeEnabled())
    await userEvent.clear(screen.getByPlaceholderText("Enter number of ranks"))
    await waitFor(() => expect(run).toBeDisabled())
  })
})

describe("TuneStep coinciding suggestions", () => {
  it("shows fastest and eco together on one row when the fastest is also cheapest", async () => {
    const both: TunerTrial = {
      id: "t9",
      status: "FINISHED",
      performance: 800,
      estimated_time: 1,
      estimated_cost: 0.5,
      np: 1,
      ntomp: 1,
      pme: "gpu",
      nb: "gpu",
    }
    mockTuner(tunerJob({ trials: [both, ECO_TRIAL] }))
    renderTune()

    expect(await screen.findByText("Fastest")).toBeInTheDocument()
    expect(screen.getByText("Eco")).toBeInTheDocument()
    // The coinciding config renders once — badges share the row; the other trial stays below.
    expect(screen.getAllByRole("radio")).toHaveLength(2)
  })
})
