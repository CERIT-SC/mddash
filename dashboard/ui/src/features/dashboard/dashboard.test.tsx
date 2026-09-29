import type { Experiment } from "@/api/generated/models"
import { mockApiBySuffix } from "@/shared/fixtures/mock-fetch"
import { renderWithProviders } from "@/shared/fixtures/render-with-providers"
import { screen, waitFor } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Dashboard } from "./dashboard"

const EXPERIMENTS = "/dash/api/experiments"

function experiment(overrides: Partial<Experiment> = {}): Experiment {
  return {
    id: "exp1",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    name: "Old run",
    latest_simulation_path: null,
    engine: "GMX",
    notebook: null,
    tuner_jobs: [],
    simulation_jobs: [],
    analysis_jobs: [],
    archived_at: null,
    archive_state: null,
    ...overrides,
  }
}

function renderDashboard(experiments: Experiment[]) {
  mockApiBySuffix({ [EXPERIMENTS]: Response.json(experiments) })
  return renderWithProviders(<Dashboard search={{}} onSearchChange={() => undefined} />)
}

const createCard = () => screen.queryByRole("link", { name: /Create your first experiment/i })

describe("Dashboard empty state", () => {
  it("shows the create card when there are no experiments at all", async () => {
    await renderDashboard([])
    await waitFor(() => expect(createCard()).not.toBeNull())
  })

  it("shows the create card on the active tab when every experiment is archived", async () => {
    await renderDashboard([experiment({ archived_at: "2026-02-01T00:00:00Z" })])
    await waitFor(() => expect(createCard()).not.toBeNull())
  })

  it("hides the create card while an active experiment is displayed", async () => {
    await renderDashboard([experiment()])
    await screen.findByText("Old run")
    expect(createCard()).toBeNull()
  })
})
