import { createRootRoute, createRoute, createRouter } from "@tanstack/react-router"

import { BASE_PATH } from "@/util/const"
import RootLayout from "@/layouts/RootLayout"
import NotFound from "@/pages/error/404"
import Home from "@/pages/Home"
import New from "@/pages/New"
import Wizard from "@/pages/Wizard"

const rootRoute = createRootRoute({
  component: RootLayout,
  notFoundComponent: NotFound,
})

const homeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: Home,
})

const newRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/new",
  component: New,
})

export interface WizardSearch {
  tab?: string
  step?: number
}

const wizardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/$id/wizard",
  component: Wizard,
  validateSearch: (search: Record<string, unknown>): WizardSearch => {
    const tab = typeof search.tab === "string" && search.tab !== "" ? search.tab : undefined
    const rawStep = typeof search.step === "string" ? Number(search.step) : search.step
    const step = typeof rawStep === "number" && Number.isInteger(rawStep) ? rawStep : undefined
    return { tab, step }
  },
})

const routeTree = rootRoute.addChildren([homeRoute, newRoute, wizardRoute])

export const router = createRouter({
  routeTree,
  basepath: BASE_PATH,
})

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}
