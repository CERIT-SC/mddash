import { useEffect, useMemo, useState } from "react"

import { Alert, Button, H1, H2, Lead, Muted, Progress, Separator } from "@e-infra/design-system"
import { Atom, RefreshCw, Square, TriangleAlert } from "lucide-react"

import {
  DetailsLog,
  FAILED_LEAD,
  HeroHeading,
  LogEntry,
  PageHero,
  StatusIcon,
  SupportNote,
  WaitHint,
} from "../components/Hero"
import { AuthedLayout } from "../components/Layouts"
import { HubApi } from "../lib/api"
import { DEV_FALLBACK_BASE_URL, getAppConfig } from "../lib/config"
import { mount } from "../lib/mount"
import { useSpawnProgress } from "../lib/progress"

interface SpawnPendingConfig {
  progressUrl: string
}

export function SpawnPendingPage() {
  const cfg = getAppConfig<SpawnPendingConfig>({
    progressUrl: `${DEV_FALLBACK_BASE_URL}api/users/user/progress`,
  })
  const { progress, currentMessage, log, status, streamEnded } = useSpawnProgress(cfg.progressUrl)
  const api = useMemo(() => new HubApi(cfg.baseUrl, cfg.xsrf), [cfg.baseUrl, cfg.xsrf])
  const [cancelling, setCancelling] = useState(false)
  const [cancelError, setCancelError] = useState<string | null>(null)
  const [retrying, setRetrying] = useState(false)
  const [retryError, setRetryError] = useState<string | null>(null)

  // Stream gone but server not ready — fall back to polling for the outcome.
  useEffect(() => {
    if (status === "ready" || status === "failed") return
    if (!streamEnded) return
    let cancelled = false
    const poll = async () => {
      try {
        const u = await api.getUser(cfg.userName)
        if (cancelled) return
        const srv = u.servers?.[""]
        if (srv?.ready) {
          window.location.reload()
        } else if (!srv) {
          window.location.href = `${cfg.baseUrl}home`
        }
      } catch {
        /* transient API errors — keep polling */
      }
    }
    void poll()
    const id = setInterval(poll, 5000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [api, cfg.userName, cfg.baseUrl, status, streamEnded])

  const retry = async () => {
    setRetrying(true)
    setRetryError(null)
    try {
      await api.startServer(cfg.userName)
      window.location.reload()
    } catch (error) {
      setRetryError(error instanceof Error ? error.message : "Could not retry starting the server.")
      setRetrying(false)
    }
  }

  const cancelStartup = async () => {
    setCancelling(true)
    setCancelError(null)
    try {
      await api.stopServer(cfg.userName)
      window.location.reload()
    } catch (error) {
      setCancelError(error instanceof Error ? error.message : "Could not cancel server startup.")
      setCancelling(false)
    }
  }

  const failed = status === "failed"
  const showProgress = !failed && !streamEnded

  return (
    <AuthedLayout
      baseUrl={cfg.baseUrl}
      userName={cfg.userName}
      adminAccess={cfg.adminAccess}
      logoutUrl={cfg.logoutUrl}
      announcement={cfg.announcement}
    >
      <PageHero>
        <StatusIcon tone={failed ? "error" : "primary"} icon={failed ? TriangleAlert : Atom} />

        <HeroHeading ariaLive>
          <H1>{failed ? "Failed to start your server" : "Starting your server…"}</H1>
          {failed ? (
            <Lead>{FAILED_LEAD}</Lead>
          ) : (
            <Muted className="text-base">You will be redirected automatically when it's ready for you.</Muted>
          )}
        </HeroHeading>

        {failed ? (
          <Button size="lg" disabled={retrying} onClick={() => void retry()}>
            <RefreshCw className={retrying ? "animate-spin" : undefined} size={16} />
            {retrying ? "Trying again…" : "Try again"}
          </Button>
        ) : null}

        {failed ? <SupportNote /> : null}

        {showProgress ? (
          <div className="flex w-72 flex-col gap-3">
            <H2>{Math.round(progress)}%</H2>
            <Progress value={progress} />
            <Muted aria-live="polite">{currentMessage ?? "Contacting the spawner…"}</Muted>
          </div>
        ) : null}

        {!failed && streamEnded ? <Muted aria-live="polite">Waiting for server to become ready…</Muted> : null}

        {!failed ? <WaitHint>This may take a few minutes</WaitHint> : null}

        {retryError ? <Alert variant="error">{retryError}</Alert> : null}
        {cancelError ? <Alert variant="error">{cancelError}</Alert> : null}

        <Separator className="w-full" />

        <DetailsLog open={failed} summary={failed ? "Event log" : "Show event log"}>
          {log.length === 0 ? (
            <LogEntry>No events yet.</LogEntry>
          ) : (
            log.map((entry, i) => (
              <LogEntry key={i} html={entry.html}>
                {entry.text}
              </LogEntry>
            ))
          )}
        </DetailsLog>

        {!failed ? (
          <Button variant="error" size="sm" disabled={cancelling} onClick={() => void cancelStartup()}>
            <Square size={16} />
            {cancelling ? "Cancelling startup…" : "Cancel startup"}
          </Button>
        ) : null}
      </PageHero>
    </AuthedLayout>
  )
}

mount(<SpawnPendingPage />)
