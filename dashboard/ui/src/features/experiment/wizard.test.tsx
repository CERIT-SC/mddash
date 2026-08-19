import type { Experiment } from "@/api/generated/models"
import { CREATE_TAB } from "@/features/simulation"
import { experiment } from "@/shared/fixtures/experiment"
import { mockApiBySuffix } from "@/shared/fixtures/mock-fetch"
import { simulation } from "@/shared/fixtures/simulation"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import { ExperimentWizard, type WizardSearch } from "./wizard"

const alpha = simulation("alpha.simulation.json", { name: "Alpha", step: 2 })
const beta = simulation("nested/beta.simulation.json", { name: "Beta", step: 3 })
const mockApi = mockApiBySuffix

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

  it("constrains very long experiment names with truncation", async () => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha]),
      "/experiments/exp1": okExperiment({ name: `Long ${"y".repeat(300)}` }),
    })
    renderWizard({})
    const button = await screen.findByRole("button", { name: "Rename experiment" })
    expect(button).toHaveClass("max-w-full")
    expect(button.querySelector("span.truncate")).toBeInTheDocument()
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
    // NB: the tab queries here target the simulations tablist; the Setup step has its own source tabs.
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha, beta]),
      "/experiments/exp1": okExperiment({ latest_simulation_path: alpha.simulation_path }),
    })
    renderWizard({ simulation: beta.simulation_path })
    expect(await screen.findByRole("tab", { name: "Alpha" })).toHaveAttribute("aria-selected", "false")
    expect(screen.getByRole("tab", { name: "Beta" })).toHaveAttribute("aria-selected", "true")
    expect(screen.queryByRole("tab", { name: "[Unnamed Simulation]" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "New simulation" })).toBeVisible()
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
    renderWizard({ simulation: "gone.simulation.json" })
    const tablist = within(await screen.findByRole("tablist", { name: "Simulations" }))
    expect((await tablist.findAllByRole("tab")).length).toBe(2)
    expect(tablist.getByRole("tab", { name: "Alpha" })).toHaveAttribute("aria-selected", "true")
  })

  it("shows the step from the URL and reports navigation through onSearchChange", async () => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha]),
      "/experiments/exp1": okExperiment(),
    })
    const changes: WizardSearch[] = []
    const user = userEvent.setup()
    renderWizard({ step: 2 }, (next) => changes.push(next))

    expect(await screen.findByText("Section 3:")).toBeInTheDocument()
    expect(screen.getByText(/Section \d+:/).parentElement).toHaveTextContent("Section 3: Run")

    await user.click(screen.getByRole("button", { name: "Next" }))
    expect(changes).toEqual([{ simulation: alpha.simulation_path, step: 3 }])

    await user.click(screen.getByRole("button", { name: "Go to section 1: Setup" }))
    expect(changes).toEqual([
      { simulation: alpha.simulation_path, step: 3 },
      { simulation: alpha.simulation_path, step: 0 },
    ])
  })

  it("falls back to the simulation's own step when the URL has none", async () => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha, beta]),
      "/experiments/exp1": okExperiment({ latest_simulation_path: beta.simulation_path }),
    })
    renderWizard({})
    expect(await screen.findByText("Section 3:")).toBeInTheDocument()
    expect(screen.getByText(/Section \d+:/).parentElement).toHaveTextContent("Section 3: Run")
  })

  it("keeps the setup source view across tab and step navigations", async () => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha, beta]),
      "/experiments/exp1": okExperiment(),
    })
    const changes: WizardSearch[] = []
    const user = userEvent.setup()
    renderWizard({ simulation: alpha.simulation_path, step: 0, source: "manual" }, (next) => changes.push(next))
    await user.click(await screen.findByRole("tab", { name: "Beta" }))
    expect(changes[changes.length - 1]).toEqual({ source: "manual", simulation: beta.simulation_path })
    // The mounted props still point at alpha until the router applies the search,
    // so the Next click navigates alpha's stepper — the source rides along regardless.
    await user.click(screen.getByRole("button", { name: "Next" }))
    expect(changes[changes.length - 1]).toEqual({ source: "manual", simulation: alpha.simulation_path, step: 1 })
  })

  it("switches simulations from the tab bar, dropping the step", async () => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha, beta]),
      "/experiments/exp1": okExperiment(),
    })
    const changes: WizardSearch[] = []
    const user = userEvent.setup()
    renderWizard({ simulation: alpha.simulation_path, step: 1 }, (next) => changes.push(next))
    await user.click(await screen.findByRole("tab", { name: "Beta" }))
    // Radix may re-fire activation (mousedown + focus) while the controlled
    // value is stale; the real route re-renders on the first navigation.
    expect(changes[changes.length - 1]).toEqual({ simulation: beta.simulation_path })
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
    expect(screen.getByText(/Section \d+:/).parentElement).toHaveTextContent("Section 1: Setup")
    expect(screen.getByRole("button", { name: "New simulation" })).toBeVisible()
  })

  it("switches to the unnamed tab from New simulation, dropping the step", async () => {
    mockApi({
      "/experiments/exp1/simulations": Response.json([alpha]),
      "/experiments/exp1": okExperiment(),
    })
    const changes: WizardSearch[] = []
    const user = userEvent.setup()
    renderWizard({ simulation: alpha.simulation_path, step: 1 }, (next) => changes.push(next))
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
    expect(screen.getByText(/Section \d+:/).parentElement).toHaveTextContent("Section 1: Setup")
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
    })
    const changes: WizardSearch[] = []
    const user = userEvent.setup()
    renderWizard({ simulation: alpha.simulation_path }, (next) => changes.push(next))
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
    renderWizard({ simulation: alpha.simulation_path, step: 1 }, (next) => changes.push(next))
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
