import { useEffect } from "react"

import { Button, H1, Muted } from "@e-infra/design-system"
import { Atom, Play, RefreshCw, TriangleAlert } from "lucide-react"

import { AuthedLayout } from "../components/Layouts"
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

/** Plain "stopped" is handled by /hub/home; this renders only failed spawns and implicit-spawn countdowns. */
export function NotRunningPage() {
  const cfg = getAppConfig<NotRunningConfig>({
    failed: false,
    serverName: "",
    spawnUrl: `${DEV_FALLBACK_BASE_URL}spawn`,
    failedMessage: null,
    failedHtmlMessage: null,
    implicitSpawnSeconds: 0,
  })

  const redirect = !cfg.failed && cfg.implicitSpawnSeconds === 0

  useEffect(() => {
    if (redirect) {
      window.location.replace(`${cfg.baseUrl}home`)
    }
  }, [redirect, cfg.baseUrl])

  // Mirror the stock not_running.html: auto-relaunch on implicit spawn.
  useEffect(() => {
    if (cfg.implicitSpawnSeconds > 0) {
      const timer = setTimeout(() => {
        window.location.href = cfg.spawnUrl
      }, 1000 * cfg.implicitSpawnSeconds)
      return () => clearTimeout(timer)
    }
  }, [cfg.implicitSpawnSeconds, cfg.spawnUrl])

  if (redirect) {
    return null
  }

  const serverLabel = cfg.serverName ? ` ${cfg.serverName}` : ""
  const ServerIcon = cfg.failed ? TriangleAlert : Atom

  return (
    <AuthedLayout
      baseUrl={cfg.baseUrl}
      userName={cfg.userName}
      adminAccess={cfg.adminAccess}
      logoutUrl={cfg.logoutUrl}
      announcement={cfg.announcement}
    >
      <div className="mx-auto flex w-full max-w-lg flex-1 flex-col items-center justify-center gap-6 text-center">
        <div
          aria-hidden="true"
          className={`flex h-16 w-16 items-center justify-center rounded-full ${
            cfg.failed ? "bg-error text-error-foreground" : "bg-primary text-primary-foreground"
          }`}
        >
          <ServerIcon size={28} />
        </div>

        <div className="flex flex-col gap-2">
          <H1>{cfg.failed ? "Spawn failed" : "Your server is offline"}</H1>
          <Muted className="text-base">
            {cfg.failed
              ? `The latest attempt to start your server${serverLabel} did not succeed.`
              : `Your personal notebook server${serverLabel} is not running.`}
          </Muted>
        </div>

        {cfg.failed ? (
          cfg.failedHtmlMessage ? (
            <Muted dangerouslySetInnerHTML={{ __html: cfg.failedHtmlMessage }} />
          ) : cfg.failedMessage ? (
            <Muted>{cfg.failedMessage}</Muted>
          ) : null
        ) : cfg.implicitSpawnSeconds > 0 ? (
          <Muted>It will be restarted automatically. If you are not redirected in a few seconds, click below.</Muted>
        ) : null}

        <Button size="lg" asChild>
          <a href={cfg.spawnUrl} className="no-underline">
            {cfg.failed ? <RefreshCw size={16} /> : <Play size={16} />}
            {cfg.failed ? "Retry" : "Start my server"}
          </a>
        </Button>

        {!cfg.failed ? (
          <Muted>This starts your personal notebook server. It usually takes up to a minute.</Muted>
        ) : null}
      </div>
    </AuthedLayout>
  )
}

mount(<NotRunningPage />)
