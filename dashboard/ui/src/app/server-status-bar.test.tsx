import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { ServerStatusBar } from "./server-status-bar"

function renderBar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ServerStatusBar user="demo" />
    </QueryClientProvider>
  )
}

describe("ServerStatusBar", () => {
  it("renders storage and uptime from metrics", async () => {
    vi.stubGlobal("fetch", async () =>
      Response.json({
        storage_limit_bytes: 100 * 1024 ** 3,
        storage_used_bytes: 40.8 * 1024 ** 3,
        uptime_seconds: 772,
      })
    )
    renderBar()
    expect(await screen.findByText("40.8 GB")).toBeVisible()
    expect(screen.getByText(/\/ 100\.0 GB/)).toBeVisible()
    expect(screen.getByText("12m 52s")).toBeVisible()
  })

  it("issues the hub stop call when stopping the server", async () => {
    Object.defineProperty(document, "cookie", { value: "_xsrf=abc123", writable: true })
    const calls: { url: string; init?: RequestInit }[] = []
    vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url
      calls.push({ url, init })
      if (url.includes("/hub/api/")) return Response.json({})
      return Response.json({})
    })
    const user = userEvent.setup()
    renderBar()
    await user.click(screen.getByRole("button", { name: "Stop server" }))
    const stop = calls.find((call) => call.url.endsWith("/hub/api/users/demo/server"))
    expect(stop).toBeDefined()
    expect(stop?.init?.method).toBe("DELETE")
    if (stop?.init?.headers) {
      expect((stop.init.headers as Record<string, string>)["X-XSRFToken"]).toBe("abc123")
    }
  })
})
