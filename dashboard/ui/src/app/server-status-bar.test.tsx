import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ServerStatusBar } from "./server-status-bar"

function renderBar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ServerStatusBar />
    </QueryClientProvider>
  )
}

function stubMetricsFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      Response.json({
        storage_limit_bytes: 100 * 1024 ** 3,
        storage_used_bytes: 40.8 * 1024 ** 3,
        uptime_seconds: 772,
      })
    )
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("ServerStatusBar", () => {
  it("renders storage and uptime from metrics", async () => {
    stubMetricsFetch()
    renderBar()
    expect(await screen.findByText("40.8 GB")).toBeVisible()
    expect(screen.getByText(/\/ 100\.0 GB/)).toBeVisible()
    expect(screen.getByText("12m 52s")).toBeVisible()
  })

  it("sends the browser to the hub home page to stop the server", async () => {
    stubMetricsFetch()
    const assign = vi.fn()
    // jsdom forbids mocking location.assign itself; replace the whole property.
    Object.defineProperty(window, "location", { value: { assign }, writable: true, configurable: true })
    const user = userEvent.setup()
    renderBar()
    await user.click(screen.getByRole("button", { name: "Stop server" }))
    expect(assign).toHaveBeenCalledWith("/hub/home?stop")
    expect(screen.getByRole("button", { name: "Stopping…" })).toBeDisabled()
  })
})
