import { useEffect } from "react"

import { Button, Card, CardContent, P } from "@e-infra/design-system"
import { CircleCheck } from "lucide-react"

import { IconCardHeader } from "../components/IconCard"
import { CenteredLayout } from "../components/Layouts"
import { DEV_FALLBACK_BASE_URL, getAppConfig } from "../lib/config"
import { mount } from "../lib/mount"

interface LogoutConfig {
  loginUrl: string
}

export function LogoutPage() {
  const cfg = getAppConfig<LogoutConfig>({
    loginUrl: `${DEV_FALLBACK_BASE_URL}login`,
  })

  // Talqo keeps its chat credential in localStorage; don't let one user's
  // conversation outlive sign-out on a shared machine. Same origin as /dash.
  useEffect(() => {
    try {
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith("talqo:")) localStorage.removeItem(key)
      }
    } catch {}
  }, [])

  return (
    <CenteredLayout announcement={cfg.announcement}>
      <Card>
        <IconCardHeader icon={CircleCheck} tone="success" title="Signed out" description="Your session has ended" />
        <CardContent className="flex flex-col gap-4">
          <P>Successfully logged out of JupyterHub.</P>
          <Button size="lg" className="w-full" asChild>
            <a href={cfg.loginUrl} className="no-underline">
              Log in again
            </a>
          </Button>
        </CardContent>
      </Card>
    </CenteredLayout>
  )
}

mount(<LogoutPage />)
