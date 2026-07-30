import { useEffect, useMemo, useState } from "react"

import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@e-infra/design-system"
import { LoaderCircle, RefreshCw } from "lucide-react"

import { AuthedLayout } from "../components/Layouts"
import { HubApi } from "../lib/api"
import { getAppConfig } from "../lib/config"
import { mount } from "../lib/mount"

export function StopPendingPage() {
  const cfg = getAppConfig({})
  const api = useMemo(() => new HubApi(cfg.baseUrl, cfg.xsrf), [cfg.baseUrl, cfg.xsrf])
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => {
      setElapsed((s) => s + 2)
      api
        .getUser(cfg.userName)
        .then((user) => {
          if (!user.pending && !(user.servers?.[""]?.active ?? false)) {
            clearInterval(timer)
            window.location.href = `${cfg.baseUrl}home`
          }
        })
        .catch(() => {
          /* transient API errors — keep polling */
        })
    }, 2000)
    return () => clearInterval(timer)
  }, [api, cfg.baseUrl, cfg.userName])

  return (
    <AuthedLayout
      baseUrl={cfg.baseUrl}
      userName={cfg.userName}
      adminAccess={cfg.adminAccess}
      logoutUrl={cfg.logoutUrl}
      announcement={cfg.announcement}
    >
      <Card className="mx-auto w-full max-w-xl">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <LoaderCircle className="text-primary animate-spin" size={20} />
            Your server is stopping
          </CardTitle>
          <CardDescription>You can start it again once it has finished stopping</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col items-start gap-4">
          <p className="text-text-muted text-sm">This usually takes a few seconds…</p>
          {elapsed >= 30 ? (
            <Button variant="secondary" onClick={() => window.location.reload()}>
              <RefreshCw size={16} />
              Refresh
            </Button>
          ) : null}
        </CardContent>
      </Card>
    </AuthedLayout>
  )
}

mount(<StopPendingPage />)
