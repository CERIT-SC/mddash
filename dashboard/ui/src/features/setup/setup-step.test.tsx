import type { FileInfo, Notebook, Simulation } from "@/api/generated/models"
import { experiment, withNotebook } from "@/shared/fixtures/experiment"
import { requestUrl } from "@/shared/fixtures/mock-fetch"
import { simulation } from "@/shared/fixtures/simulation"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SetupStep } from "./setup-step"

const API_NOTEBOOK = "/experiments/exp1/notebook"
const SERVE = "/dash/notebook/exp1/?token=tok"
const CONFIG = "/notebook-config"
const EXPERIMENTS = "/dash/api/experiments"

function ipynb(path: string): FileInfo {
  return { name: path.split("/").pop() ?? path, size: 10, path, url: `/files/${path}` }
}

function notebook(overrides: Partial<Notebook> = {}): Notebook {
  return {
    id: 1,
    experiment_id: "exp1",
    token: "tok",
    gpu: false,
    path: SERVE,
    status: "DOWN",
    started_at: null,
    ...overrides,
  }
}

const NOTEBOOK_CONFIG = {
  tiers: [
    { value: "1x", cpuLimit: "5", memoryLimit: "8Gi" },
    { value: "2x", cpuLimit: "10", memoryLimit: "16Gi" },
  ],
  defaultTier: "1x",
}

function mockSetup({
  notebooks = notebook(),
  sims = [] as Simulation[],
  ipynbs = [] as FileInfo[],
  experimentsList = [] as ReturnType<typeof experiment>[],
  concurrentLimit = 2,
} = {}) {
  const simState = { current: sims }
  const calls: { url: string; method: string; body?: unknown }[] = []
  vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input)
    calls.push({
      url,
      method: init?.method ?? "GET",
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
    })
    if (url.endsWith(CONFIG)) return Response.json({ ...NOTEBOOK_CONFIG, concurrentLimit })
    if (url.endsWith(API_NOTEBOOK)) return Response.json(notebooks)
    if (url.endsWith(SERVE)) return new Response(null, { status: 200 })
    if (url.endsWith(EXPERIMENTS)) return Response.json(experimentsList)
    if (url.endsWith("/experiments/exp1/simulations")) return Response.json([...simState.current])
    if (url.endsWith("files?ext=ipynb")) return Response.json(ipynbs)
    if (url.includes("files?ext=")) return Response.json([])
    return new Response(null, { status: 404 })
  })
  return { simState, calls }
}

function renderSetup(props: Partial<React.ComponentProps<typeof SetupStep>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const spies = {
    onOpenSimulation: props.onOpenSimulation ?? vi.fn(),
    onSourceChange: props.onSourceChange ?? vi.fn(),
    onContinue: props.onContinue ?? vi.fn(),
  }
  render(
    <QueryClientProvider client={client}>
      <SetupStep
        experimentId="exp1"
        experiment={experiment("exp1")}
        simulation={undefined}
        creating
        source="notebook"
        onOpenSimulation={spies.onOpenSimulation}
        onSourceChange={spies.onSourceChange}
        onContinue={spies.onContinue}
        {...props}
      />
    </QueryClientProvider>
  )
  return spies
}

afterEach(() => {
  vi.useRealTimers()
})

describe("SetupStep", () => {
  it("greets a fresh simulation tab with the guided notebook start", async () => {
    mockSetup()
    renderSetup()

    expect(await screen.findByRole("heading", { name: "Set up your simulation" })).toBeVisible()
    const guide = screen.getByRole("region", { name: "Setup guide" })
    expect(within(guide).getByText("Start the notebook")).toBeVisible()
    expect(within(guide).getByText("1", { selector: "span" })).toHaveAttribute("aria-current", "step")
    const launcher = within(guide).getByLabelText("Notebook launcher")
    expect(await within(launcher).findByRole("combobox", { name: "Notebook size" })).toBeVisible()
    expect(within(launcher).getByRole("checkbox", { name: "GPU" })).not.toBeChecked()
    expect(within(launcher).getByRole("button", { name: "Start notebook" })).toBeEnabled()
    expect(within(guide).getByText(/Run Pipeline/)).toBeVisible()
    expect(screen.queryByText(/Wait for the run/)).not.toBeInTheDocument()
    expect(screen.queryByText("New simulation")).not.toBeInTheDocument()
  })

  it("starts the notebook with the default tier", async () => {
    const { calls } = mockSetup()
    const user = userEvent.setup()
    renderSetup()
    await user.click(await screen.findByRole("button", { name: "Start notebook" }))
    expect(calls).toContainEqual({
      url: "/dash/api/experiments/exp1/notebook",
      method: "POST",
      body: { tier: "1x", gpu: false },
    })
  })

  it("defers the start into the quota dialog when the notebook limit is full", async () => {
    const { calls } = mockSetup({
      concurrentLimit: 1,
      experimentsList: [experiment("exp2", { name: "Busy A", notebook: withNotebook("RUNNING", "exp2") })],
    })
    const user = userEvent.setup()
    renderSetup()
    const start = await screen.findByRole("button", { name: "Start notebook" })
    // Proactive deferral requires the quota queries to have settled.
    await vi.waitFor(() => {
      expect(calls.some((call) => call.url.endsWith(CONFIG))).toBe(true)
      expect(calls.some((call) => call.url.endsWith(EXPERIMENTS))).toBe(true)
    })

    await user.click(start)
    const dialog = await screen.findByRole("dialog")
    expect(within(dialog).getByText("Notebook limit reached")).toBeVisible()
    expect(calls.find((call) => call.method === "POST")).toBeUndefined()
  })

  it("advances to the pipeline step once the notebook serves, deep-linking setup.ipynb", async () => {
    mockSetup({
      notebooks: notebook({ status: "RUNNING", started_at: new Date().toISOString() }),
      ipynbs: [ipynb("setup.ipynb")],
    })
    renderSetup()

    const guide = screen.getByRole("region", { name: "Setup guide" })
    expect(await within(guide).findByLabelText("Step 1 done")).toBeInTheDocument()
    const open = await within(guide).findByRole("link", { name: "Open notebook" })
    expect(open).toHaveAttribute("href", "/dash/notebook/exp1/lab/tree/setup.ipynb?token=tok")
    expect(open).toHaveAttribute("target", "_blank")
    expect(within(guide).getByText("Wait for the run to finish.")).toBeVisible()
    expect(within(guide).getByText("Go to Tune")).toBeVisible()
  })

  it("shows the already-set-up manifest with badges next to a fully checked guide", async () => {
    const existing = simulation("protein.simulation.json", {
      name: "protein",
      valid: true,
      step: 1,
      files: {
        run_input: "production/protein.tpr",
        reference_structure: "analysis/ref.gro",
        trajectory: "production/protein.xtc",
      },
    })
    mockSetup({ notebooks: notebook({ status: "RUNNING", started_at: new Date().toISOString() }), sims: [existing] })
    renderSetup({ simulation: existing, creating: false })

    const guide = screen.getByRole("region", { name: "Setup guide" })
    expect(await within(guide).findByLabelText("Step 1 done")).toBeInTheDocument()
    expect(await within(guide).findByLabelText("Step 2 done")).toBeInTheDocument()
    expect(within(guide).getByText("Check the validity of data below and move on to tune.")).toBeVisible()

    expect(await screen.findByText("GROMACS")).toBeInTheDocument()
    expect(screen.getByText("Valid")).toBeInTheDocument()
    expect(screen.getByDisplayValue("protein")).toBeEnabled()
    expect(screen.getByRole("button", { name: "Save changes" })).toBeInTheDocument()
  })

  it("disables Go to Tune while no simulation exists", async () => {
    mockSetup()
    renderSetup()
    expect(await screen.findByRole("button", { name: "Go to Tune" })).toBeDisabled()
  })

  it("reports Go to Tune as a step change once a simulation exists", async () => {
    const existing = simulation("protein.simulation.json", { name: "protein", valid: true, step: 1 })
    mockSetup({ sims: [existing] })
    const user = userEvent.setup()
    const { onContinue } = renderSetup({ simulation: existing, creating: false })
    await user.click(await screen.findByRole("button", { name: "Go to Tune" }))
    expect(onContinue).toHaveBeenCalledTimes(1)
  })

  it("reports the Manual tab as a source change instead of flipping local state", async () => {
    mockSetup()
    const user = userEvent.setup()
    const { onSourceChange } = renderSetup()

    await user.click(await screen.findByRole("tab", { name: "Manual" }))
    expect(onSourceChange).toHaveBeenCalledWith("manual")
    expect(screen.getByRole("tab", { name: "From Notebook" })).toHaveAttribute("aria-selected", "true")
  })

  it("shows the manual creation form when the URL says Manual", async () => {
    mockSetup()
    renderSetup({ source: "manual" })

    expect(await screen.findByText("New simulation")).toBeVisible()
    expect(screen.getByPlaceholderText("Enter name of your choice")).toBeVisible()
    expect(screen.getAllByLabelText("Notebook launcher").length).toBeGreaterThan(0)
  })

  it("stops a running notebook from the launcher, not just the top bar", async () => {
    const { calls } = mockSetup({ notebooks: notebook({ status: "RUNNING", started_at: new Date().toISOString() }) })
    const user = userEvent.setup()
    renderSetup({ source: "manual" })

    await user.click(await screen.findByRole("button", { name: "Stop notebook" }))
    expect(calls).toContainEqual({ url: "/dash/api/experiments/exp1/notebook", method: "DELETE", body: undefined })
  })

  it("adopts a manifest the pipeline produces while waiting", async () => {
    vi.useFakeTimers()
    const { simState } = mockSetup({ notebooks: notebook({ status: "RUNNING", started_at: new Date().toISOString() }) })
    const { onOpenSimulation } = renderSetup()

    // flush the initial queries (empty list snapshot) through the fake clock
    await act(async () => await vi.advanceTimersByTimeAsync(100))
    expect(onOpenSimulation).not.toHaveBeenCalled()

    simState.current = [simulation("fresh.simulation.json", { name: "protein", valid: true })]
    await act(async () => await vi.advanceTimersByTimeAsync(5_100))
    expect(onOpenSimulation).toHaveBeenCalledWith("fresh.simulation.json")
    // The URL updates asynchronously; further polls before then must not adopt again.
    await act(async () => await vi.advanceTimersByTimeAsync(5_100))
    expect(onOpenSimulation).toHaveBeenCalledTimes(1)
  })
})
