import { SiteHeader } from "@/app/site-header"
import { ApiErrorAlert } from "@/shared/ui/api-error-alert"
import { Content } from "@e-infra/design-system"
import { Outlet, useRouteContext, type ErrorComponentProps } from "@tanstack/react-router"

export function AppShell() {
  const { config } = useRouteContext({ from: "__root__" })
  return (
    <div className="bg-background text-text min-h-screen">
      <SiteHeader
        user={config.user}
        hubHomeUrl={config.hubHomeUrl}
        hubTokenUrl={config.hubTokenUrl}
        logoutUrl={config.logoutUrl}
      />
      <main>
        <Content>
          <Outlet />
        </Content>
      </main>
    </div>
  )
}

export function RouteError({ error, reset }: ErrorComponentProps) {
  return <ApiErrorAlert error={error} onRetry={reset} />
}
