import { SiteHeader } from "@/shared/ui/site-header"
import { Alert, AlertDescription, AlertTitle, Content } from "@e-infra/design-system"
import { Outlet, useRouteContext } from "@tanstack/react-router"

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

export function RouteError() {
  return (
    <Alert role="alert" variant="error">
      <AlertTitle>Page unavailable</AlertTitle>
      <AlertDescription>This page could not be displayed. Reload the dashboard or contact support.</AlertDescription>
    </Alert>
  )
}
