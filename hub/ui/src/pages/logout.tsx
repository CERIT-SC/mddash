import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, P } from "@e-infra/design-system"
import { CircleCheck } from "lucide-react"

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

  return (
    <CenteredLayout announcement={cfg.announcement}>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CircleCheck className="text-success" size={20} />
            Signed out
          </CardTitle>
          <CardDescription>Your session has ended</CardDescription>
        </CardHeader>
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
