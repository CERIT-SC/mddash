import { AppShell, RouteError } from "@/app/app-shell"
import type { RuntimeConfig } from "@/app/config/runtime-config"
import { createRootRouteWithContext } from "@tanstack/react-router"

type RouterContext = { config: RuntimeConfig }

export const Route = createRootRouteWithContext<RouterContext>()({
  component: AppShell,
  errorComponent: RouteError,
})
