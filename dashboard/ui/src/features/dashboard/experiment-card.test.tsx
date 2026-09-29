import type { Experiment } from "@/api/generated/models"
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
