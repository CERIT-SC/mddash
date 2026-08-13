import type { Experiment } from "@/api/generated/models"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { Welcome } from "./welcome"

const experiment = (id: string): Experiment => ({
  id,
  name: `Experiment ${id}`,
  created_at: "2026-08-13T00:00:00Z",
  updated_at: "2026-08-13T00:00:00Z",
  source_message: null,
  engine: "GMX",
  notebook: null,
  tuner_jobs: [],
  simulation_jobs: [],
  analysis_jobs: [],
})

function renderWelcome() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Welcome user="alice" />
    </QueryClientProvider>
  )
}

function mockFetchResponses(...responses: Response[]) {
  const queue = [...responses]
  vi.stubGlobal("fetch", async () => queue.shift() ?? new Response("[]", { status: 200 }))
}

describe("Welcome", () => {
  it.each([
    [[], "No experiments yet"],
    [[experiment("one")], "1 experiment"],
    [[experiment("one"), experiment("two")], "2 experiments"],
  ])("shows the experiment count", async (experiments, expected) => {
    mockFetchResponses(Response.json(experiments))
    renderWelcome()
    expect(await screen.findByText(expected)).toBeVisible()
  })

  it("shows problem details and retries a failed response", async () => {
    mockFetchResponses(
      Response.json(
        { type: "urn:mddash:upstream-unavailable", title: "Unavailable", detail: "Try later" },
        { status: 503 }
      ),
      Response.json([experiment("recovered")])
    )
    const user = userEvent.setup()
    renderWelcome()
    expect(await screen.findByRole("alert")).toHaveTextContent("urn:mddash:upstream-unavailable")
    await user.click(screen.getByRole("button", { name: "Retry" }))
    expect(await screen.findByText("1 experiment")).toBeVisible()
  })

  it("retains the personalized heading while loading", () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    renderWelcome()
    expect(screen.getByRole("heading", { name: "Welcome, alice" })).toBeVisible()
    expect(screen.getByText("Loading experiment count")).toBeVisible()
  })
})
