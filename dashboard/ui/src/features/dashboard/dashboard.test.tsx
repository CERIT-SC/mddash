import { experiment, withNotebook } from "@/shared/fixtures/experiment"
import { mockFetch } from "@/shared/fixtures/mock-fetch"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import { Dashboard } from "./dashboard"

function renderDashboard(search = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Dashboard search={search} onSearchChange={() => undefined} />
    </QueryClientProvider>
  )
}

describe("Dashboard", () => {
  it("groups experiments by notebook state with counts", async () => {
    mockFetch(
      Response.json([
        experiment("one", { notebook: withNotebook("RUNNING") }),
        experiment("two", { notebook: withNotebook("DOWN") }),
        experiment("three"),
      ])
    )
    renderDashboard()
    const running = await screen.findByRole("heading", { name: /notebook running/i })
    expect(within(running).getByText("1")).toBeVisible()
    const stopped = screen.getByRole("heading", { name: /notebook stopped/i })
    expect(within(stopped).getByText("2")).toBeVisible()
    expect(screen.getByText("Experiment one")).toBeVisible()
    expect(screen.getByText("Experiment three")).toBeVisible()
  })

  it("filters experiments by search query", async () => {
    mockFetch(
      Response.json([experiment("alpha", { name: "Analyze protein" }), experiment("beta", { name: "Tuning membrane" })])
    )
    renderDashboard({ q: "membrane" })
    expect(await screen.findByText("Tuning membrane")).toBeVisible()
    expect(screen.queryByText("Analyze protein")).not.toBeInTheDocument()
  })

  it("shows an empty state when there are no experiments", async () => {
    mockFetch(Response.json([]))
    renderDashboard()
    expect(await screen.findByText("No experiments yet.")).toBeVisible()
  })

  it("shows a no-match state when the search filters everything out", async () => {
    mockFetch(Response.json([experiment("alpha", { name: "Analyze" })]))
    renderDashboard({ q: "zzz" })
    expect(await screen.findByText("No experiments match “zzz”.")).toBeVisible()
  })

  it("shows problem details and retries a failed response", async () => {
    mockFetch(
      Response.json(
        { type: "urn:mddash:upstream-unavailable", title: "Unavailable", detail: "Try later" },
        { status: 503 }
      ),
      Response.json([experiment("recovered")])
    )
    const user = userEvent.setup()
    renderDashboard()
    expect(await screen.findByRole("alert")).toHaveTextContent("urn:mddash:upstream-unavailable")
    await user.click(screen.getByRole("button", { name: "Retry" }))
    expect(await screen.findByText("Experiment recovered")).toBeVisible()
  })

  it("disables unimplemented features", async () => {
    mockFetch(Response.json([experiment("one")]))
    renderDashboard()
    expect(await screen.findByRole("button", { name: /new/i })).toBeDisabled()
    expect(screen.getByRole("tab", { name: /archived/i })).toBeDisabled()
  })
})
