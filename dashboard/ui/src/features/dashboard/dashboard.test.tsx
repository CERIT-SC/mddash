import type { Experiment } from "@/api/generated/models"
import { withNotebook, withPopulation } from "@/shared/fixtures/experiment"
import { mockApiBySuffix } from "@/shared/fixtures/mock-fetch"
import { renderWithProviders } from "@/shared/fixtures/render-with-providers"
import { screen, waitFor } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Dashboard, type DashboardSearch } from "./dashboard"

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
    population: null,
    tuner_jobs: [],
    simulation_jobs: [],
    analysis_jobs: [],
    archived_at: null,
    archive_state: null,
    ...overrides,
  }
}

function renderDashboard(experiments: Experiment[], search: DashboardSearch = {}) {
  mockApiBySuffix({ [EXPERIMENTS]: Response.json(experiments) })
  return renderWithProviders(<Dashboard search={search} onSearchChange={() => undefined} />)
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

  it("shows a zero badge on the archived tab, same as the active tab", async () => {
    await renderDashboard([experiment()])
    expect(await screen.findByRole("tab", { name: "Archived 0" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Active 1" })).toBeInTheDocument()
  })

  it("shows the search no-match text instead of the create card", async () => {
    await renderDashboard([experiment()], { q: "nope" })
    expect(await screen.findByText("No experiments match “nope”.")).toBeInTheDocument()
    expect(createCard()).toBeNull()
  })
})

describe("Dashboard populating group", () => {
  it("shows an unfinished import under Populating and keeps it out of the notebook groups", async () => {
    await renderDashboard([
      experiment({
        id: "pop1",
        name: "Import run",
        population: withPopulation("pop1", { status: "running", phase: "downloading", files_present: 3 }),
        // even a running notebook does not pull it into the notebook groups
        notebook: withNotebook("RUNNING", "pop1"),
      }),
      experiment({ id: "nb1", name: "Notebook run", notebook: withNotebook("RUNNING", "nb1") }),
    ])

    expect(await screen.findByRole("heading", { name: "Populating 1" })).toBeInTheDocument()
    // The notebook group counts only the experiment without an unfinished import.
    expect(screen.getByRole("heading", { name: "Notebook running 1" })).toBeInTheDocument()
    expect(screen.queryByRole("heading", { name: /notebook stopped/i })).not.toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Import run" })).toBeInTheDocument()
  })

  it("keeps failed and cancelled imports in the Populating group until deletion", async () => {
    await renderDashboard([
      experiment({
        id: "f1",
        name: "Failed import",
        population: withPopulation("f1", { status: "failed", error: "The repository could not be fetched." }),
      }),
      experiment({ id: "c1", name: "Cancelled import", population: withPopulation("c1", { status: "cancelled" }) }),
    ])

    expect(await screen.findByRole("heading", { name: "Populating 2" })).toBeInTheDocument()
    expect(screen.queryByRole("heading", { name: /notebook/i })).not.toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Failed import" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Cancelled import" })).toBeInTheDocument()
  })
})
