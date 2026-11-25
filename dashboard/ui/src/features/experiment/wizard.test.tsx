import type { Simulation } from "@/api/generated/models"
import { experiment, withPopulation } from "@/shared/fixtures/experiment"
import { mockApiBySuffix } from "@/shared/fixtures/mock-fetch"
import { renderWithProviders } from "@/shared/fixtures/render-with-providers"
import { simulation } from "@/shared/fixtures/simulation"
import { screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ExperimentWizard } from "./wizard"

const SIM = "md.simulation.json"

function renderWizard(overrides: Partial<Simulation> = {}) {
  mockApiBySuffix({
    "/experiments/exp1/simulations": Response.json([simulation(SIM, { valid: true, ...overrides })]),
    "/experiments/exp1": Response.json(experiment("exp1", { latest_simulation_path: SIM, can_publish: false })),
  })
  return renderWithProviders(<ExperimentWizard experimentId="exp1" search={{}} onSearchChange={vi.fn()} />)
}

async function renderPopulationWizard(population: Parameters<typeof withPopulation>[1]) {
  const calls = mockApiBySuffix({
    "/experiments/exp1": Response.json(experiment("exp1", { population: withPopulation("exp1", population) })),
  })
  await renderWithProviders(<ExperimentWizard experimentId="exp1" search={{}} onSearchChange={vi.fn()} />)
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe("ExperimentWizard implicit landing", () => {
  it("lands on Tune while the simulation is tuning", async () => {
    await renderWizard({ step: 1, status: "tuning", live: true })
    expect(await screen.findByText("Section 2 of 5: Tune")).toBeInTheDocument()
  })

  it("lands on Tune once tuning has results but no run was submitted", async () => {
    await renderWizard({ step: 2, status: "tuning" })
    expect(await screen.findByText("Section 2 of 5: Tune")).toBeInTheDocument()
  })

  it("holds Setup for a valid manifest that never tuned", async () => {
    await renderWizard({ step: 1, status: "setup complete" })
    expect(await screen.findByText("Section 1 of 5: Setup")).toBeInTheDocument()
  })

  it("tracks the ladder once a run exists", async () => {
    await renderWizard({ step: 2, status: "simulating", live: true })
    expect(await screen.findByText("Section 3 of 5: Run")).toBeInTheDocument()
  })
})

describe("ExperimentWizard population gate", () => {
  it("shows the read-only population page instead of the wizard while the import runs", async () => {
    const calls = await renderPopulationWizard({
      status: "running",
      phase: "downloading",
      files_present: 2,
      files_total: 8,
      bytes_present: 51200,
      bytes_total: 204800,
      byte_percentage: 25,
    })

    expect(await screen.findByText(/downloading the repository/i)).toBeInTheDocument()
    expect(screen.getByText(/2 of 8 files present/)).toBeInTheDocument()
    expect(screen.getByText("25%")).toBeInTheDocument()
    // No rename control and no wizard steps while the import is unfinished.
    expect(screen.queryByRole("button", { name: "Rename experiment" })).not.toBeInTheDocument()
    expect(screen.queryByText(/section 1 of 5/i)).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: /cancel import/i })).toBeInTheDocument()
    // No simulation manifest can exist yet: the simulations query stays disabled.
    expect(calls.some((call) => call.url.endsWith("/experiments/exp1/simulations"))).toBe(false)
  })

  it("keeps a failed import on the population page with its safe error", async () => {
    await renderPopulationWizard({
      status: "failed",
      error: "The repository could not be fetched.",
      files_present: 1,
      bytes_present: 1024,
    })

    expect(await screen.findByText("Import failed")).toBeInTheDocument()
    expect(screen.getByText("The repository could not be fetched.")).toBeInTheDocument()
    // Last measured counters are retained next to the failure.
    expect(screen.getByText(/1 file present/)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /cancel import/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/section 1 of 5/i)).not.toBeInTheDocument()
  })

  it("keeps a failed cancellation visible with its retry", async () => {
    await renderPopulationWizard({
      status: "cancelling",
      phase: "cancelling",
      error: "The repository download could not be cancelled yet. Try the cancellation again.",
    })

    expect(await screen.findByText("Cancellation not finished")).toBeInTheDocument()
    expect(screen.getByText(/could not be cancelled yet/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /cancel import/i })).toBeInTheDocument()
  })

  it("lists dataset files renamed by the import above the wizard", async () => {
    mockApiBySuffix({
      "/experiments/exp1/simulations": Response.json([simulation(SIM, { valid: true })]),
      "/experiments/exp1": Response.json(
        experiment("exp1", {
          latest_simulation_path: SIM,
          population: withPopulation("exp1", {
            status: "succeeded",
            renamed_paths: ["README.dataset.md", "LICENSE.dataset"],
          }),
        })
      ),
    })
    await renderWithProviders(<ExperimentWizard experimentId="exp1" search={{}} onSearchChange={vi.fn()} />)

    expect(await screen.findByText("2 dataset files were renamed")).toBeInTheDocument()
    expect(screen.getByText("README.dataset.md")).toBeInTheDocument()
    expect(screen.getByText("Section 1 of 5: Setup")).toBeInTheDocument()
  })

  it("shows a cancelled import as a durable terminal state", async () => {
    await renderPopulationWizard({ status: "cancelled" })

    expect(await screen.findByText("Import cancelled")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /cancel import/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/section 1 of 5/i)).not.toBeInTheDocument()
  })
})
