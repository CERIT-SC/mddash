import { useState } from "react"

import type { RuntimeConfig } from "@/app/config/runtime-config"
import { createAppRouter } from "@/app/router"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider } from "@tanstack/react-router"

type AppProvidersProps = { config: RuntimeConfig }

export function AppProviders({ config }: AppProvidersProps) {
  const [queryClient] = useState(() => new QueryClient())
  const [router] = useState(() => createAppRouter(config))
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}
