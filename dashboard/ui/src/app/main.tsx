import { StrictMode } from "react"

import { initializeApiRuntime } from "@/api/runtime"
import { loadRuntimeConfig } from "@/app/config"
import { AppProviders } from "@/app/providers/app-providers"
import { Alert, AlertDescription, AlertTitle } from "@e-infra/design-system"
import { createRoot } from "react-dom/client"

import "@/app/styles/index.css"

const rootElement = document.getElementById("root")
if (!rootElement) throw new Error("Application root is unavailable")
const root = createRoot(rootElement)

async function start(): Promise<void> {
  const config = await loadRuntimeConfig()
  initializeApiRuntime(config.apiPath)
  root.render(
    <StrictMode>
      <AppProviders config={config} />
    </StrictMode>
  )
}

start().catch(() => {
  root.render(
    <main className="bg-background text-text min-h-screen p-4 md:p-6 lg:p-8">
      <Alert role="alert" variant="error" className="mx-auto max-w-xl">
        <AlertTitle>Dashboard configuration error</AlertTitle>
        <AlertDescription>
          The dashboard could not start because its deployment configuration is invalid.
        </AlertDescription>
      </Alert>
    </main>
  )
})
