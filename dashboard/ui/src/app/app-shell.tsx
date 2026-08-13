import { toApiError } from "@/api/errors"
import { SiteHeader } from "@/app/site-header"
import { Alert, AlertDescription, AlertTitle, Button, Content } from "@e-infra/design-system"
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
  const apiError = toApiError(error)
  return (
    <Alert role="alert" variant="error">
      <AlertTitle>{apiError.title}</AlertTitle>
      <AlertDescription>
        <p>{apiError.message}</p>
        {apiError.type ? <p className="text-text-muted text-xs">Support ID: {apiError.type}</p> : null}
        <Button className="mt-4" size="sm" onClick={reset}>
          Retry
        </Button>
      </AlertDescription>
    </Alert>
  )
}
