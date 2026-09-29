import type { Simulation } from "@/api/generated/models"
import { experiment } from "@/shared/fixtures/experiment"
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
