import { useEffect } from "react"

import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, P } from "@e-infra/design-system"
import { RefreshCw, Rocket } from "lucide-react"

import { CenteredLayout } from "../components/Layouts"
import { DEV_FALLBACK_BASE_URL, getAppConfig } from "../lib/config"
import { mount } from "../lib/mount"

interface NotRunningConfig {
  failed: boolean
  serverName: string
  spawnUrl: string
  failedMessage: string | null
  failedHtmlMessage: string | null
  /** Seconds until the hub restarts the server automatically (0 = never). */
  implicitSpawnSeconds: number
}

export function NotRunningPage() {
  const cfg = getAppConfig<NotRunningConfig>({
    failed: false,
    serverName: "",
    spawnUrl: `${DEV_FALLBACK_BASE_URL}spawn`,
    failedMessage: null,
    failedHtmlMessage: null,
    implicitSpawnSeconds: 0,
  })

  // Mirror the stock not_running.html: auto-relaunch on implicit spawn.
  useEffect(() => {
    if (cfg.implicitSpawnSeconds > 0) {
      const timer = setTimeout(() => {
        window.location.href = cfg.spawnUrl
      }, 1000 * cfg.implicitSpawnSeconds)
      return () => clearTimeout(timer)
    }
  }, [cfg.implicitSpawnSeconds, cfg.spawnUrl])

  return (
    <CenteredLayout>
      <Card>
        <CardHeader>
          <CardTitle>{cfg.failed ? "Spawn failed" : "Server not running"}</CardTitle>
          <CardDescription>
            {cfg.failed ? "The latest launch attempt did not succeed" : "Your workspace is offline"}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {cfg.failed ? (
            <>
              <P>
                The latest attempt to start your server{cfg.serverName ? ` ${cfg.serverName}` : ""} has failed. Would
                you like to retry starting it?
              </P>
              {cfg.failedHtmlMessage ? (
                <P className="text-text-muted" dangerouslySetInnerHTML={{ __html: cfg.failedHtmlMessage }} />
              ) : cfg.failedMessage ? (
                <P className="text-text-muted">{cfg.failedMessage}</P>
              ) : null}
            </>
          ) : (
            <P>
              Your server{cfg.serverName ? ` ${cfg.serverName}` : ""} is not running.
              {cfg.implicitSpawnSeconds > 0
                ? " It will be restarted automatically. If you are not redirected in a few seconds, click below to launch it."
                : " Would you like to start it?"}
            </P>
          )}
          <Button size="lg" className="w-full" asChild>
            <a href={cfg.spawnUrl} className="no-underline">
              {cfg.failed ? <RefreshCw size={16} /> : <Rocket size={16} />}
              {cfg.failed ? "Relaunch" : "Launch"} server{cfg.serverName ? ` ${cfg.serverName}` : ""}
            </a>
          </Button>
        </CardContent>
      </Card>
    </CenteredLayout>
  )
}

mount(<NotRunningPage />)
