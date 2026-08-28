import { ServerStatusBar } from "@/app/server-status-bar"
import { SiteHeader } from "@/app/site-header"
import { NotebookStatusBar } from "@/features/notebook"
import { ApiErrorAlert } from "@/shared/ui/api-error-alert"
import { Content, Toaster } from "@e-infra/design-system"
import { Outlet, useParams, useRouteContext, type ErrorComponentProps } from "@tanstack/react-router"

export function AppShell() {
  const { config } = useRouteContext({ from: "__root__" })
  const { experimentId } = useParams({ strict: false })
  return (
    <div className="bg-background text-text min-h-screen">
      <SiteHeader user={config.user} />
      <main>
        {/* Attached to the header like the mock; kept out of Content's padding.
            Experiment pages swap in the notebook controller — server controls don't belong there. */}
        <div className="relative z-10 flex justify-center px-4">
          {experimentId ? <NotebookStatusBar experimentId={experimentId} /> : <ServerStatusBar />}
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
