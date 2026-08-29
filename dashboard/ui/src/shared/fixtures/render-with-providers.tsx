import type { ReactNode } from "react"

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router"
import { render } from "@testing-library/react"

/**
 * Renders ui inside a QueryClient and a minimal memory router so components with
 * Link work outside the app. The routeTree stub mirrors the app paths the
 * components link to; the router is pre-loaded so the first paint is synchronous.
 * The returned view also carries `router` for location assertions.
 */
export async function renderWithProviders(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute({ component: () => ui })
  const wizardRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/experiments/$experimentId",
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([wizardRoute]),
    history: createMemoryHistory(),
  })
  await router.load()
  const view = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
  return Object.assign(view, { router })
}
