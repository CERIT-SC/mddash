import { useEffect } from "react"

import { Button, H1, Lead, Muted, Separator } from "@e-infra/design-system"
import { Atom, Play, RefreshCw, TriangleAlert } from "lucide-react"

import {
  DetailsLog,
  FAILED_LEAD,
  HeroHeading,
  LogEntry,
  PageHero,
  START_HINT,
  StatusIcon,
  SupportNote,
} from "../components/Hero"
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

  return (
    <AuthedLayout
      baseUrl={cfg.baseUrl}
      userName={cfg.userName}
      adminAccess={cfg.adminAccess}
      logoutUrl={cfg.logoutUrl}
      announcement={cfg.announcement}
    >
      <PageHero>
        <StatusIcon tone={cfg.failed ? "error" : "primary"} icon={cfg.failed ? TriangleAlert : Atom} />

        <HeroHeading>
          <H1>{cfg.failed ? "Failed to start your server" : "Your server is offline"}</H1>
          {cfg.failed ? (
            <Lead>{FAILED_LEAD}</Lead>
          ) : (
            <Muted className="text-base">{`Your personal notebook server${serverLabel} is not running.`}</Muted>
          )}
        </HeroHeading>

        {!cfg.failed && cfg.implicitSpawnSeconds > 0 ? (
          <Muted>It will be restarted automatically. If you are not redirected in a few seconds, click below.</Muted>
        ) : null}

        <Button size="lg" asChild>
          <a href={cfg.spawnUrl} className="no-underline">
            {cfg.failed ? <RefreshCw size={16} /> : <Play size={16} />}
            {cfg.failed ? "Try again" : "Start my server"}
          </a>
        </Button>

        {cfg.failed ? <SupportNote /> : null}

        {cfg.failed ? <Separator className="w-full" /> : null}

        {cfg.failed ? (
          <DetailsLog open summary="Event log">
            {cfg.failedHtmlMessage ? (
              <LogEntry html={cfg.failedHtmlMessage} />
            ) : cfg.failedMessage ? (
              <LogEntry>{cfg.failedMessage}</LogEntry>
            ) : (
              <LogEntry>No failure details available.</LogEntry>
            )}
          </DetailsLog>
        ) : null}

        {!cfg.failed ? <Muted>{START_HINT}</Muted> : null}
      </PageHero>
    </AuthedLayout>
  )
}

mount(<NotRunningPage />)
