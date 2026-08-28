import type { RuntimeConfig } from "@/app/config/runtime-config"
import { mockApiBySuffix } from "@/shared/fixtures/mock-fetch"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router"
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { AppShell } from "./app-shell"

const CONFIG = {
  basePath: "/dash",
  apiPath: "/dash/api",
  user: "demo",
  defaultNotebooksRepo: "https://example.test/notebooks.git",
  mdpositUrl: "https://mdposit.example.test",
} satisfies RuntimeConfig

const NOTEBOOK_API = "/experiments/exp1/notebook"
const SERVE = "/dash/notebook/exp1/?token=tok"

const METRICS = Response.json({ storage_used_bytes: null, storage_limit_bytes: null, uptime_seconds: 5 })
const RUNNING_NOTEBOOK = Response.json({
  id: 1,
  experiment_id: "exp1",
  token: "tok",
  tier: "1x",
  gpu: false,
  path: SERVE,
  status: "RUNNING",
  started_at: new Date(Date.now() - 5_000).toISOString(),
})

async function renderShell(path: string, handlers: Record<string, Response>) {
  mockApiBySuffix(handlers)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute({ component: AppShell })
  const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: () => null })
  const wizardRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/experiments/$experimentId",
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute, wizardRoute]),
    history: createMemoryHistory({ initialEntries: [path] }),
    context: { config: CONFIG },
  })
  await router.load()
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

describe("AppShell status bar swap", () => {
  it("shows the server status bar on the dashboard", async () => {
    await renderShell("/", { "/metrics": METRICS })

    expect(await screen.findByRole("region", { name: "Server status" })).toBeVisible()
    expect(screen.queryByRole("region", { name: "Notebook status" })).not.toBeInTheDocument()
  })

  it("shows the notebook controller instead on the experiment page", async () => {
    await renderShell("/experiments/exp1", {
      "/metrics": METRICS,
      [NOTEBOOK_API]: RUNNING_NOTEBOOK,
      [SERVE]: new Response(null, { status: 200 }),
    })

    expect(await screen.findByRole("region", { name: "Notebook status" })).toBeVisible()
    // the server bar is never substituted back in on the experiment route,
    // and a down notebook hides the controller entirely (widget-level coverage)
    expect(screen.queryByRole("region", { name: "Server status" })).not.toBeInTheDocument()
  })
})
