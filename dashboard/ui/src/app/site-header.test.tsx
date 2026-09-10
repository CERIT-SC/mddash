import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { SiteHeader } from "./site-header"

function renderHeader() {
  const rootRoute = createRootRoute({
    component: () => <SiteHeader user="alice" />,
  })
  const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: () => null })
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

describe("SiteHeader", () => {
  it("toggles the theme when persistence is unavailable", async () => {
    const user = userEvent.setup()
    vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
      throw new DOMException("Blocked", "SecurityError")
    })
    renderHeader()
    const toggle = await screen.findByRole("button", { name: "Switch to dark theme" })
    await user.click(toggle)
    expect(document.documentElement).toHaveClass("dark")
    expect(screen.getByRole("button", { name: "Switch to light theme" })).toBeVisible()
  })
})
