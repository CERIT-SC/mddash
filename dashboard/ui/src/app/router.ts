import type { RuntimeConfig } from "@/app/config/runtime-config"
import { routeTree } from "@/routeTree.gen"
import { createRouter } from "@tanstack/react-router"

export function createAppRouter(config: RuntimeConfig) {
  return createRouter({ routeTree, basepath: config.basePath, context: { config } })
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>
  }
}
