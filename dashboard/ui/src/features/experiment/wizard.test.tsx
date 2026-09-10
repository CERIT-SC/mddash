import type { Experiment } from "@/api/generated/models"
import { CREATE_TAB, simulationParam } from "@/features/simulation"
import { experiment } from "@/shared/fixtures/experiment"
import { mockApiBySuffix, requestUrl } from "@/shared/fixtures/mock-fetch"
import { simulation } from "@/shared/fixtures/simulation"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ExperimentWizard, type WizardSearch } from "./wizard"

afterEach(() => {
  vi.useRealTimers()
})

const alpha = simulation("alpha.simulation.json", { name: "Alpha", step: 2 })
const beta = simulation("nested/beta.simulation.json", { name: "Beta", step: 2, status: "tuning" })
const mockApi = mockApiBySuffix

/** Minimal running GMX job — keeps a mounted Run step from auto-navigating back to Tune. */
function runningGmxJob(simulationPath: string) {
  return Response.json({
    id: "job1",
    experiment_id: "exp1",
    simulation_path: simulationPath,
    created_at: "2026-08-19T00:00:00Z",
    engine: "GMX",
    np: 1,
    ntomp: 1,
    pme: "cpu",
    nb: "cpu",
    status: "RUNNING",
    nsteps: 100,
    nsteps_done: 50,
    estimated_time: 60,
  })
}

function okExperiment(overrides: Partial<Experiment> = {}) {
  return Response.json(experiment("exp1", { name: "Membrane study", ...overrides }))
}

function renderWizard(search: WizardSearch = {}, onSearchChange: (next: WizardSearch) => void = () => undefined) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ExperimentWizard experimentId="exp1" search={search} onSearchChange={onSearchChange} />
    </QueryClientProvider>
  )
}

describe("ExperimentWizard", () => {
  it("renders the title row with the rename chip and metadata", async () => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha]),
      "/experiments/exp1": okExperiment({
        source: { type: "pdb", pdb_id: "1L2Y", files: [] },
        created_at: "2026-07-20T13:43:20Z",
        notebooks_repo: "https://github.com/sb-ncbr/mddash-notebooks.git",
      }),
    })
    renderWizard({})
    expect(await screen.findByRole("heading", { name: "Experiment" })).toBeVisible()
    expect(screen.getByRole("button", { name: "Rename experiment" })).toHaveTextContent("Membrane study")
    expect(screen.getByText("RCSB PDB (1L2Y)")).toBeVisible()
    expect(screen.getByText("Jul 20, 2026")).toBeVisible()
    expect(screen.getByText("sb-ncbr/mddash-notebooks.git")).toBeVisible()
  })

  it("hides metadata items the API has no values for", async () => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha]),
      "/experiments/exp1": okExperiment({ source: null, notebooks_repo: null }),
    })
    renderWizard({})
    expect(await screen.findByRole("heading", { name: "Experiment" })).toBeVisible()
    expect(screen.getByText("Aug 13, 2026")).toBeVisible()
    expect(screen.queryByText(/github\.com/)).not.toBeInTheDocument()
    expect(screen.queryByText("·")).not.toBeInTheDocument()
  })

  it("renames the experiment from the title chip", async () => {
    const calls = mockApi({
      "/experiments/exp1/simulations": Response.json([alpha]),
      "/experiments/exp1": okExperiment(),
    })
    const user = userEvent.setup()
    renderWizard({})
    await user.click(await screen.findByRole("button", { name: "Rename experiment" }))
    const input = screen.getByLabelText("Name")
    await user.clear(input)
    await user.type(input, "Renamed study")
    await user.click(screen.getByRole("button", { name: "Save" }))
    expect(calls).toContainEqual({
      url: "/dash/api/experiments/exp1",
      method: "PATCH",
      body: { name: "Renamed study" },
    })
  })

  it("renders one tab per simulation, preselecting the URL simulation", async () => {
    // The simulations tablist — the Setup step has its own source tabs.
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha, beta]),
      "/experiments/exp1": okExperiment({ latest_simulation_path: alpha.simulation_path }),
    })
    renderWizard({ simulation: simulationParam(beta.simulation_path) })
    expect(await screen.findByRole("tab", { name: "Alpha" })).toHaveAttribute("aria-selected", "false")
    expect(screen.getByRole("tab", { name: "Beta" })).toHaveAttribute("aria-selected", "true")
    expect(screen.queryByRole("tab", { name: "[Unnamed Simulation]" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "New simulation" })).toBeVisible()
  })

  it("still selects the tab from a legacy suffixed URL simulation", async () => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha, beta]),
      "/experiments/exp1": okExperiment(),
    })
    renderWizard({ simulation: beta.simulation_path })
    expect(await screen.findByRole("tab", { name: "Beta" })).toHaveAttribute("aria-selected", "true")
  })

  it.each([
    ["latest simulation", { latest_simulation_path: beta.simulation_path }, "Beta"],
    ["first simulation", { latest_simulation_path: null }, "Alpha"],
  ])("defaults to the %s tab without a URL simulation", async (_label, overrides, expected) => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha, beta]),
      "/experiments/exp1": okExperiment(overrides),
    })
    renderWizard({})
    expect(
      (await within(await screen.findByRole("tablist", { name: "Simulations" })).findAllByRole("tab")).length
    ).toBe(2)
    expect(
      within(screen.getByRole("tablist", { name: "Simulations" })).getByRole("tab", { name: expected })
    ).toHaveAttribute("aria-selected", "true")
  })

  it("falls back to the default tab when the URL simulation is unknown", async () => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha, beta]),
      "/experiments/exp1": okExperiment(),
    })
    renderWizard({ simulation: "gone" })
    const tablist = within(await screen.findByRole("tablist", { name: "Simulations" }))
    expect((await tablist.findAllByRole("tab")).length).toBe(2)
    expect(tablist.getByRole("tab", { name: "Alpha" })).toHaveAttribute("aria-selected", "true")
  })

  it("shows the step from the URL and reports navigation through onSearchChange", async () => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha]),
      "/experiments/exp1": okExperiment(),
      [`/experiments/exp1/gmx/${alpha.simulation_path}`]: runningGmxJob(alpha.simulation_path),
    })
    const changes: WizardSearch[] = []
    const user = userEvent.setup()
    renderWizard({ step: 2 }, (next) => changes.push(next))

    expect(await screen.findByRole("button", { name: "Go to section 3: Run" })).toHaveAttribute("aria-current", "step")
    expect(
      screen.getByRole("button", { name: "Go to section 1: Setup" }).querySelector("svg.lucide-check")
    ).not.toBeNull()
    expect(screen.getByRole("button", { name: "Go to section 4: Analyze" })).toBeDisabled()

    await user.click(screen.getByRole("button", { name: "Go to section 2: Tune" }))
    expect(changes).toEqual([{ simulation: simulationParam(alpha.simulation_path), step: 1 }])

    await user.click(screen.getByRole("button", { name: "Go to section 1: Setup" }))
    expect(changes).toEqual([
      { simulation: simulationParam(alpha.simulation_path), step: 1 },
      { simulation: simulationParam(alpha.simulation_path), step: 0 },
    ])
  })

  it("lands on Run while a run is in flight (live simulation)", async () => {
    const runningBeta = simulation("nested/beta.simulation.json", {
      name: "Beta",
      step: 2,
      status: "simulating",
      live: true,
    })
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha, runningBeta]),
      "/experiments/exp1": okExperiment({ latest_simulation_path: runningBeta.simulation_path }),
      [`/experiments/exp1/gmx/${runningBeta.simulation_path}`]: runningGmxJob(runningBeta.simulation_path),
    })
    renderWizard({})
    expect(await screen.findByRole("button", { name: "Go to section 3: Run" })).toHaveAttribute("aria-current", "step")
    expect(screen.getByRole("button", { name: "Go to section 4: Analyze" })).toBeDisabled()
  })

  it("enables markers up to the simulation's API-reported step", async () => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha]),
      "/experiments/exp1": okExperiment(),
      [`/experiments/exp1/gmx/${alpha.simulation_path}`]: runningGmxJob(alpha.simulation_path),
    })
    const changes: WizardSearch[] = []
    const user = userEvent.setup()
    renderWizard({}, (next) => changes.push(next))

    expect(await screen.findByRole("button", { name: "Go to section 3: Run" })).toHaveAttribute("aria-current", "step")
    for (const name of ["Go to section 1: Setup", "Go to section 2: Tune", "Go to section 3: Run"]) {
      expect(screen.getByRole("button", { name })).toBeEnabled()
    }
    for (const name of ["Go to section 4: Analyze", "Go to section 5: Publish"]) {
      expect(screen.getByRole("button", { name })).toBeDisabled()
    }

    await user.click(screen.getByRole("button", { name: "Go to section 4: Analyze" }))
    expect(changes).toEqual([])
  })

  it("stays on Setup when the pipeline completes the manifest mid-wait", async () => {
    vi.useFakeTimers()
    const simState = { current: [simulation(alpha.simulation_path, { name: "Alpha", step: 0 })] }
    vi.stubGlobal("fetch", async (input: RequestInfo | URL): Promise<Response> => {
      const url = requestUrl(input)
      if (url.endsWith("/experiments/exp1/simulations")) return Response.json([...simState.current])
      if (url.endsWith("/experiments/exp1")) return okExperiment()
      if (url.endsWith("/notebook-config"))
        return Response.json({
          tiers: [{ value: "1x", cpuLimit: "1", memoryLimit: "4Gi" }],
          defaultTier: "1x",
          concurrentLimit: 2,
        })
      if (url.endsWith("/dash/api/experiments")) return Response.json([])
      if (url.endsWith("/experiments/exp1/notebook"))
        return Response.json({
          id: 1,
          experiment_id: "exp1",
          token: "tok",
          gpu: false,
          path: "/dash/notebook/exp1/?token=tok",
          status: "DOWN",
          started_at: null,
        })
      if (url.includes("/files?")) return Response.json([])
      return new Response(null, { status: 404 })
    })
    renderWizard({ simulation: simulationParam(alpha.simulation_path) })
    // Flush the initial queries through the fake clock.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })
    expect(screen.getByRole("heading", { name: "Set up your simulation" })).toBeVisible()

    // The notebook validates the manifest server-side.
    simState.current = [
      simulation(alpha.simulation_path, { name: "Alpha", valid: true, step: 1, status: "setup complete" }),
    ]
    // >5s crosses the Setup step's 5s manifest poll.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_100)
    })

    expect(screen.getByRole("heading", { name: "Set up your simulation" })).toBeVisible()
    expect(screen.getByRole("button", { name: "Go to Tune" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "Go to section 2: Tune" })).toBeEnabled()
  })

  it("lands on Analyze once the run finished", async () => {
    const done = simulation("done.simulation.json", { name: "Done", step: 3, status: "analyzing" })
    mockApi({
      "/experiments/exp1/simulations": Response.json([done]),
      "/experiments/exp1": okExperiment({ latest_simulation_path: done.simulation_path }),
    })
    renderWizard({})

    expect(await screen.findByRole("button", { name: "Go to section 4: Analyze" })).toHaveAttribute(
      "aria-current",
      "step"
    )
    // The simulation ladder must never reach the experiment-level Publish marker.
    expect(screen.getByRole("button", { name: "Go to section 5: Publish" })).toBeDisabled()
  })

  it("locks Publish while the viewed simulation is live, even with can_publish", async () => {
    const liveAlpha = simulation(alpha.simulation_path, { name: "Alpha", step: 3, status: "simulating", live: true })
    mockApi({
      "/experiments/exp1/simulations": Response.json([liveAlpha]),
      "/experiments/exp1": okExperiment({ can_publish: true }),
      [`/experiments/exp1/gmx/${liveAlpha.simulation_path}`]: runningGmxJob(liveAlpha.simulation_path),
    })
    renderWizard({ step: 3 })

    expect(await screen.findByRole("button", { name: "Go to section 4: Analyze" })).toHaveAttribute(
      "aria-current",
      "step"
    )
    expect(screen.getByRole("button", { name: "Go to section 5: Publish" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Publish" })).toBeDisabled()
  })

  it("keeps Publish open on a finished simulation while another one runs", async () => {
    const finished = simulation(alpha.simulation_path, { name: "Alpha", step: 3, status: "analyzing" })
    const running = simulation(beta.simulation_path, { name: "Beta", step: 3, status: "simulating", live: true })
    mockApi({
      "/experiments/exp1/simulations": Response.json([finished, running]),
      "/experiments/exp1": okExperiment({ can_publish: true, latest_simulation_path: finished.simulation_path }),
    })
    renderWizard({})

    expect(await screen.findByRole("button", { name: "Go to section 4: Analyze" })).toHaveAttribute(
      "aria-current",
      "step"
    )
    expect(screen.getByRole("button", { name: "Go to section 5: Publish" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "Publish" })).toBeEnabled()
  })

  it("refetches the experiment once the last live simulation settles, unlocking Publish", async () => {
    vi.useFakeTimers()
    const state = {
      sims: [simulation(alpha.simulation_path, { name: "Alpha", step: 3, status: "simulating", live: true })],
      exp: experiment("exp1", { can_publish: false }),
    }
    vi.stubGlobal("fetch", async (input: RequestInfo | URL): Promise<Response> => {
      const url = requestUrl(input)
      if (url.endsWith("/experiments/exp1/simulations")) return Response.json([...state.sims])
      if (url.endsWith("/experiments/exp1")) return Response.json(state.exp)
      return new Response(null, { status: 404 })
    })
    renderWizard({})
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })
    expect(screen.getByRole("button", { name: "Go to section 5: Publish" })).toBeDisabled()

    state.sims = [simulation(alpha.simulation_path, { name: "Alpha", step: 3, status: "analyzing" })]
    state.exp = experiment("exp1", { can_publish: true })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_100)
    })

    expect(screen.getByRole("button", { name: "Go to section 5: Publish" })).toBeEnabled()
  })

  it("unlocks Publish experiment-wide once the API reports can_publish", async () => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha]),
      "/experiments/exp1": okExperiment({ can_publish: true }),
      [`/experiments/exp1/gmx/${alpha.simulation_path}`]: runningGmxJob(alpha.simulation_path),
    })
    renderWizard({ simulation: simulationParam(alpha.simulation_path) })

    expect(await screen.findByRole("button", { name: "Go to section 3: Run" })).toHaveAttribute("aria-current", "step")
    // Alpha's own ladder stays at Run (per-simulation); can_publish opens ONLY
    // the experiment-level Publish marker — Tune/Run/Analyze stay gated per sim.
    expect(screen.getByRole("button", { name: "Go to section 4: Analyze" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Go to section 5: Publish" })).toBeEnabled()
  })

  it("ignores a URL step that is not unlocked (stale Publish bookmark)", async () => {
    // Bookmarked with can_publish true; now false — content falls back to the
    // simulation's own progress, never the locked Publish step.
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha]),
      "/experiments/exp1": okExperiment({ can_publish: false }),
      [`/experiments/exp1/gmx/${alpha.simulation_path}`]: runningGmxJob(alpha.simulation_path),
    })
    renderWizard({ step: 4 })
    expect(await screen.findByRole("button", { name: "Go to section 3: Run" })).toHaveAttribute("aria-current", "step")
    expect(await screen.findByRole("heading", { name: "Run your simulation" })).toBeVisible()
  })

  it("shows Publish from the URL when can_publish is true", async () => {
    mockApi({
      "/experiments/exp1/publish/status": Response.json({
        experiment_id: "exp1",
        mdrepo_id: "rec1",
        draft_url: "https://mdrepo.example/uploads/rec1",
        upload_state: "completed",
        reason: null,
        total_files: 5,
        completed_files: 5,
        total_bytes: 1024,
        completed_bytes: 1024,
      }),
      "/dash/api/mdrepo/status": Response.json({ authenticated: false }),
      "/experiments/exp1/simulations": Response.json([alpha]),
      "/experiments/exp1": okExperiment({ can_publish: true }),
      [`/experiments/exp1/gmx/${alpha.simulation_path}`]: runningGmxJob(alpha.simulation_path),
    })
    renderWizard({ step: 4 })
    expect(await screen.findByRole("button", { name: "Go to section 5: Publish" })).toHaveAttribute(
      "aria-current",
      "step"
    )
  })

  it("keeps the setup source view across tab and step navigations", async () => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha, beta]),
      "/experiments/exp1": okExperiment(),
    })
    const changes: WizardSearch[] = []
    const user = userEvent.setup()
    renderWizard({ simulation: simulationParam(alpha.simulation_path), step: 0, source: "manual" }, (next) =>
      changes.push(next)
    )
    await user.click(await screen.findByRole("tab", { name: "Beta" }))
    expect(changes[changes.length - 1]).toEqual({
      source: "manual",
      simulation: simulationParam(beta.simulation_path),
    })
    // The mounted props still point at alpha until the router applies the search,
    // so the marker click navigates alpha's stepper — the source rides along regardless.
    await user.click(screen.getByRole("button", { name: "Go to section 2: Tune" }))
    expect(changes[changes.length - 1]).toEqual({
      source: "manual",
      simulation: simulationParam(alpha.simulation_path),
      step: 1,
    })
  })

  it("switches simulations from the tab bar, dropping the step", async () => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha, beta]),
      "/experiments/exp1": okExperiment(),
    })
    const changes: WizardSearch[] = []
    const user = userEvent.setup()
    renderWizard({ simulation: simulationParam(alpha.simulation_path), step: 1 }, (next) => changes.push(next))
    await user.click(await screen.findByRole("tab", { name: "Beta" }))
    // Radix may re-fire activation (mousedown + focus) while the controlled
    // value is stale; the real route re-renders on the first navigation.
    expect(changes[changes.length - 1]).toEqual({ simulation: simulationParam(beta.simulation_path) })
    expect(changes.every((change) => change.step === undefined)).toBe(true)
  })

  it("shows only the unnamed tab, selected, when the experiment has no simulations", async () => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([]),
      "/experiments/exp1": okExperiment(),
    })
    renderWizard({})
    expect(await screen.findByRole("tab", { name: "[Unnamed Simulation]" })).toHaveAttribute("aria-selected", "true")
    expect(within(screen.getByRole("tablist", { name: "Simulations" })).getAllByRole("tab").length).toBe(1)
    expect(screen.getByRole("button", { name: "Go to section 1: Setup" })).toHaveAttribute("aria-current", "step")
    expect(screen.getByRole("button", { name: "New simulation" })).toBeVisible()
  })

  it("switches to the unnamed tab from New simulation, dropping the step", async () => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha]),
      "/experiments/exp1": okExperiment(),
    })
    const changes: WizardSearch[] = []
    const user = userEvent.setup()
    renderWizard({ simulation: simulationParam(alpha.simulation_path), step: 1 }, (next) => changes.push(next))
    await user.click(await screen.findByRole("button", { name: "New simulation" }))
    expect(changes[changes.length - 1]).toEqual({ simulation: CREATE_TAB })
  })

  it("activates the unnamed tab from the URL and always shows the setup step", async () => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha, beta]),
      "/experiments/exp1": okExperiment(),
    })
    renderWizard({ simulation: CREATE_TAB, step: 3 })
    expect(await screen.findByRole("tab", { name: "[Unnamed Simulation]" })).toHaveAttribute("aria-selected", "true")
    expect(screen.getByRole("button", { name: "Go to section 1: Setup" })).toHaveAttribute("aria-current", "step")
  })

  it("deletes a simulation from its tab menu after confirmation", async () => {
    const calls = mockApi({
      "/experiments/exp1/simulations/alpha.simulation.json": new Response(null, { status: 204 }),
      "/experiments/exp1/simulations": Response.json([alpha, beta]),
      "/experiments/exp1": okExperiment(),
    })
    const user = userEvent.setup()
    renderWizard({})
    await user.click(await screen.findByRole("button", { name: "Actions for Alpha" }))
    await user.click(screen.getByRole("menuitem", { name: "Delete" }))
    await user.click(screen.getByRole("button", { name: "Delete simulation" }))
    expect(calls).toContainEqual({
      url: expect.stringContaining("/experiments/exp1/simulations/alpha.simulation.json"),
      method: "DELETE",
      body: undefined,
    })
  })

  it("keeps the URL selection when deleting a different tab", async () => {
    mockApi({
      "/experiments/exp1/simulations/beta.simulation.json": new Response(null, { status: 204 }),
      "/experiments/exp1/simulations": Response.json([alpha, beta]),
      "/experiments/exp1": okExperiment(),
      // alpha defaults to its own step (2 = Run); the mounted Run step needs its job.
      [`/experiments/exp1/gmx/${alpha.simulation_path}`]: runningGmxJob(alpha.simulation_path),
    })
    const changes: WizardSearch[] = []
    const user = userEvent.setup()
    renderWizard({ simulation: simulationParam(alpha.simulation_path) }, (next) => changes.push(next))
    await user.click(await screen.findByRole("button", { name: "Actions for Beta" }))
    await user.click(screen.getByRole("menuitem", { name: "Delete" }))
    await user.click(screen.getByRole("button", { name: "Delete simulation" }))
    await waitFor(() => expect(screen.queryByRole("button", { name: "Delete simulation" })).not.toBeInTheDocument())
    expect(changes).toEqual([])
  })

  it("drops the URL selection after deleting the selected simulation", async () => {
    mockApi({
      "/experiments/exp1/simulations/alpha.simulation.json": new Response(null, { status: 204 }),
      "/experiments/exp1/simulations": Response.json([alpha, beta]),
      "/experiments/exp1": okExperiment(),
    })
    const changes: WizardSearch[] = []
    const user = userEvent.setup()
    renderWizard({ simulation: simulationParam(alpha.simulation_path), step: 1 }, (next) => changes.push(next))
    await user.click(await screen.findByRole("button", { name: "Actions for Alpha" }))
    await user.click(screen.getByRole("menuitem", { name: "Delete" }))
    await user.click(screen.getByRole("button", { name: "Delete simulation" }))
    await waitFor(() => expect(changes).toContainEqual({}))
  })

  it("shows problem details for a missing experiment", async () => {
    mockApi({
      "/experiments/exp1": Response.json(
        { type: "urn:mddash:not-found", title: "Not Found", detail: "Experiment exp1 does not exist" },
        { status: 404 }
      ),
    })
    renderWizard({})
    expect(await screen.findByRole("alert")).toHaveTextContent("urn:mddash:not-found")
  })
})
