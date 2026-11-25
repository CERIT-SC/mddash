import type { Experiment } from "@/api/generated/models"
import { withPopulation } from "@/shared/fixtures/experiment"
import { mockApiBySuffix } from "@/shared/fixtures/mock-fetch"
import { renderWithProviders } from "@/shared/fixtures/render-with-providers"
import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import { ExperimentCard } from "./experiment-card"

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

describe("ExperimentCard archiving", () => {
  it("freezes the card from the archive click, without waiting for the list refetch", async () => {
    mockApiBySuffix({
      "/dash/api/experiments/exp1/archive": Response.json({ attempt_id: "a1" }, { status: 202 }),
    })
    await renderWithProviders(<ExperimentCard experiment={experiment()} />)
    const user = userEvent.setup()

    expect(screen.getByRole("link", { name: "Old run" })).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Actions for Old run" }))
    await user.click(await screen.findByRole("menuitem", { name: "Archive" }))
    await user.click(await screen.findByRole("button", { name: "Archive experiment" }))

    // No list query is mounted here, so only the mutation state can freeze the card.
    await waitFor(() => expect(screen.queryByRole("link", { name: "Old run" })).toBeNull())
    await user.click(screen.getByRole("button", { name: "Actions for Old run" }))
    expect(screen.getByRole("menuitem", { name: "Rename" })).toHaveAttribute("aria-disabled", "true")
    expect(screen.getByRole("menuitem", { name: "Delete" })).toHaveAttribute("aria-disabled", "true")
  })
})

describe("ExperimentCard population", () => {
  it("shows measured progress and only cancel while the import is active", async () => {
    const calls = mockApiBySuffix({
      "/dash/api/experiments/exp1/population/cancel": Response.json(
        { data: experiment({ population: withPopulation("exp1", { status: "cancelling" }) }) },
        { status: 200 }
      ),
    })
    const user = userEvent.setup()
    await renderWithProviders(
      <ExperimentCard
        experiment={experiment({
          population: withPopulation("exp1", {
            status: "running",
            phase: "downloading",
            files_present: 3,
            files_total: 10,
            bytes_present: 51200,
            bytes_total: 204800,
            byte_percentage: 25,
          }),
        })}
      />
    )

    // The counters say "files present", never completed or validated files.
    expect(await screen.findByText(/downloading the repository/i)).toBeInTheDocument()
    expect(screen.getByText("3 of 10 files present · 50 KB of 200 KB")).toBeInTheDocument()
    expect(screen.getByText("25%")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Actions for Old run" }))
    expect(await screen.findByRole("menuitem", { name: "Cancel import" })).toBeInTheDocument()
    for (const name of ["Rename", "Start notebook", "Archive", "Delete"]) {
      expect(screen.queryByRole("menuitem", { name })).not.toBeInTheDocument()
    }

    await user.click(screen.getByRole("menuitem", { name: "Cancel import" }))
    await user.click(await screen.findByRole("button", { name: "Cancel import" }))
    await waitFor(() =>
      expect(calls.some((call) => call.method === "POST" && call.url.endsWith("/population/cancel"))).toBe(true)
    )
  })

  it("keeps a failed import visible with its safe error and offers deletion", async () => {
    const calls = mockApiBySuffix({
      "/dash/api/experiments/exp1": new Response(null, { status: 204 }),
    })
    const user = userEvent.setup()
    await renderWithProviders(
      <ExperimentCard
        experiment={experiment({
          population: withPopulation("exp1", {
            status: "failed",
            error: "The repository could not be fetched.",
            files_present: 2,
            bytes_present: 51200,
          }),
        })}
      />
    )

    // Durable inline failure, last measured counters kept, no spinner.
    expect(await screen.findByText("Import failed")).toBeInTheDocument()
    expect(screen.getByText("The repository could not be fetched.")).toBeInTheDocument()
    expect(screen.getByText("2 files present · 50 KB")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Actions for Old run" }))
    expect(await screen.findByRole("menuitem", { name: "Delete" })).toBeInTheDocument()
    expect(screen.queryByRole("menuitem", { name: "Cancel import" })).not.toBeInTheDocument()

    await user.click(screen.getByRole("menuitem", { name: "Delete" }))
    await user.click(await screen.findByRole("button", { name: "Delete experiment" }))
    await waitFor(() =>
      expect(calls.some((call) => call.method === "DELETE" && call.url.endsWith("/dash/api/experiments/exp1"))).toBe(
        true
      )
    )
  })

  it("shows a cancelled import as a neutral durable state with deletion", async () => {
    mockApiBySuffix({})
    await renderWithProviders(
      <ExperimentCard experiment={experiment({ population: withPopulation("exp1", { status: "cancelled" }) })} />
    )

    expect(await screen.findByText("Import cancelled")).toBeInTheDocument()
    // nothing was downloaded, so no counter row
    expect(screen.queryByText(/files present/)).not.toBeInTheDocument()
  })
})
