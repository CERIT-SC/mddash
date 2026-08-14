import { ServerStatusBar } from "@/app/server-status-bar"
import { SiteHeader } from "@/app/site-header"
import { ApiErrorAlert } from "@/shared/ui/api-error-alert"
import { Content, Toaster } from "@e-infra/design-system"
import { Outlet, useRouteContext, type ErrorComponentProps } from "@tanstack/react-router"

export function AppShell() {
  const { config } = useRouteContext({ from: "__root__" })
  return (
    <div className="bg-background text-text min-h-screen">
      <SiteHeader user={config.user} />
      <main>
        {/* Attached to the header like the mock; kept out of Content's padding. */}
        <div className="relative z-10 flex justify-center px-4">
          <ServerStatusBar user={config.user} />
        </div>
        <Content>
          <Outlet />
        </Content>
      </main>
      <Toaster position="top-center" richColors />
    </div>
  )
}

export function RouteError({ error, reset }: ErrorComponentProps) {
  return <ApiErrorAlert error={error} onRetry={reset} />
}
