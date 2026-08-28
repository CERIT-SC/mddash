import { experiment, withNotebook } from "@/shared/fixtures/experiment"
import { mockApiBySuffix, requestUrl } from "@/shared/fixtures/mock-fetch"
import { EXPERIMENTS_URL, NOTEBOOK_CONFIG_URL, notebookConfigResponse } from "@/shared/fixtures/notebook-quota"
import { renderWithProviders } from "@/shared/fixtures/render-with-providers"
import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { Dashboard, type DashboardSearch } from "./dashboard"

function renderDashboard(search: DashboardSearch = {}) {
  return renderWithProviders(
    <Dashboard
      search={search}
      onSearchChange={() => undefined}
      defaultNotebooksRepo="https://example.test/notebooks.git"
    />
  )
}

describe("Dashboard", () => {
  it("groups experiments by notebook state with counts against the concurrent limit", async () => {
    mockApiBySuffix({
      [EXPERIMENTS_URL]: Response.json([
        experiment("one", { notebook: withNotebook("RUNNING") }),
        experiment("two", { notebook: withNotebook("DOWN") }),
        experiment("three"),
      ]),
      [NOTEBOOK_CONFIG_URL]: notebookConfigResponse(2),
    })
    await renderDashboard()
    const running = await screen.findByRole("heading", { name: /notebook running/i })
    expect(within(running).getByText("1/2")).toBeVisible()
    const stopped = screen.getByRole("heading", { name: /notebook stopped/i })
    expect(within(stopped).getByText("2")).toBeVisible()
    expect(screen.getByText("Experiment one")).toBeVisible()
    expect(screen.getByText("Experiment three")).toBeVisible()
  })

  it("falls back to a plain running count while the limit is unavailable", async () => {
    mockApiBySuffix({
      [EXPERIMENTS_URL]: Response.json([experiment("one", { notebook: withNotebook("RUNNING") })]),
      [NOTEBOOK_CONFIG_URL]: new Response(null, { status: 404 }),
    })
    await renderDashboard()
    const running = await screen.findByRole("heading", { name: /notebook running/i })
    expect(within(running).getByText("1")).toBeVisible()
    expect(within(running).queryByText(/\/2/)).not.toBeInTheDocument()
  })

  it("filters experiments by search query", async () => {
    mockApiBySuffix({
      [EXPERIMENTS_URL]: Response.json([
        experiment("alpha", { name: "Analyze protein" }),
        experiment("beta", { name: "Tuning membrane" }),
      ]),
      [NOTEBOOK_CONFIG_URL]: notebookConfigResponse(),
    })
    await renderDashboard({ q: "membrane" })
    expect(await screen.findByText("Tuning membrane")).toBeVisible()
    expect(screen.queryByText("Analyze protein")).not.toBeInTheDocument()
  })

  it("shows an empty state when there are no experiments", async () => {
    mockApiBySuffix({ [EXPERIMENTS_URL]: Response.json([]), [NOTEBOOK_CONFIG_URL]: notebookConfigResponse() })
    await renderDashboard()
    expect(await screen.findByText("No experiments yet.")).toBeVisible()
  })

  it("shows a no-match state when the search filters everything out", async () => {
    mockApiBySuffix({
      [EXPERIMENTS_URL]: Response.json([experiment("alpha", { name: "Analyze" })]),
      [NOTEBOOK_CONFIG_URL]: notebookConfigResponse(),
    })
    await renderDashboard({ q: "zzz" })
    expect(await screen.findByText("No experiments match “zzz”.")).toBeVisible()
  })

  it("shows problem details and retries a failed response", async () => {
    let experimentsCalls = 0
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      const url = requestUrl(input)
      if (url.endsWith(EXPERIMENTS_URL)) {
        experimentsCalls += 1
        return experimentsCalls === 1
          ? Response.json(
              { type: "urn:mddash:upstream-unavailable", title: "Unavailable", detail: "Try later" },
              { status: 503 }
            )
          : Response.json([experiment("recovered")])
      }
      return new Response(null, { status: 404 })
    })
    const user = userEvent.setup()
    await renderDashboard()
    expect(await screen.findByRole("alert")).toHaveTextContent("urn:mddash:upstream-unavailable")
    await user.click(screen.getByRole("button", { name: "Retry" }))
    expect(await screen.findByText("Experiment recovered")).toBeVisible()
  })

  it("disables unimplemented features", async () => {
    mockApiBySuffix({
      [EXPERIMENTS_URL]: Response.json([experiment("one")]),
      [NOTEBOOK_CONFIG_URL]: notebookConfigResponse(),
    })
    await renderDashboard()
    expect(await screen.findByRole("button", { name: /new/i })).toBeEnabled()
    expect(screen.getByRole("tab", { name: /archived/i })).toBeDisabled()
  })
})
