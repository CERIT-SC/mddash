import { useEffect, useMemo, useState } from "react"

import { Alert, Button, H1, H2, Muted, Progress, Separator } from "@e-infra/design-system"
import { Atom, Clock, RotateCw, Square, TriangleAlert } from "lucide-react"

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
        // transient
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
      <div className="mx-auto flex w-full max-w-lg flex-1 flex-col items-center justify-center gap-6 text-center">
        <div
          aria-hidden="true"
          className={`flex h-16 w-16 items-center justify-center rounded-full ${
            failed ? "bg-error text-error-foreground" : "bg-primary text-primary-foreground"
          }`}
        >
          {failed ? <TriangleAlert size={28} /> : <Atom size={28} />}
        </div>

        <div className="flex flex-col gap-2">
          <H1>{failed ? "Failed to start your server" : "Starting your server…"}</H1>
          <Muted className="text-base">
            {failed
              ? "The server could not be started. Try starting it again."
              : "You will be redirected automatically when it's ready for you."}
          </Muted>
        </div>

        {failed ? (
          <Alert variant="error" className="flex items-start gap-2 text-left">
            <TriangleAlert size={16} />
            <span>
              The server failed to start.{currentMessage ? ` ${currentMessage}` : ""}
              {retryError ? ` ${retryError}` : ""}
            </span>
          </Alert>
        ) : null}

        {showProgress ? (
          <div className="flex w-72 flex-col gap-3">
            <H2>{Math.round(progress)}%</H2>
            <Progress value={progress} />
            <Muted aria-live="polite">{currentMessage ?? "Contacting the spawner…"}</Muted>
          </div>
        ) : null}

        {!failed && streamEnded ? <Muted aria-live="polite">Waiting for server to become ready…</Muted> : null}

        {!failed ? (
          <div className="flex items-center gap-1">
            <Clock size={14} aria-hidden="true" className="text-text-muted" />
            <Muted>This may take a few minutes</Muted>
          </div>
        ) : null}

        {cancelError ? <Alert variant="error">{cancelError}</Alert> : null}

        <Separator className="w-full" />

        <details open={failed} className="bg-surface w-full rounded-md p-3 text-left">
          <summary className="text-text-muted cursor-pointer text-sm">{failed ? "Event log" : "Show event log"}</summary>
          <div className="mt-2 flex flex-col gap-1">
            {log.length === 0 ? (
              <span className="text-text-muted text-xs">No events yet.</span>
            ) : (
              log.map((entry, i) =>
                entry.html ? (
                  <span key={i} className="text-text-muted text-xs" dangerouslySetInnerHTML={{ __html: entry.html }} />
                ) : (
                  <span key={i} className="text-text-muted text-xs">
                    {entry.text}
                  </span>
                )
              )
            )}
          </div>
        </details>

        {failed ? (
          <Button variant="secondary" size="sm" disabled={retrying} onClick={() => void retry()}>
            <RotateCw className={retrying ? "animate-spin" : undefined} size={16} />
            {retrying ? "Retrying…" : "Retry starting server"}
          </Button>
        ) : (
          <Button variant="error" size="sm" disabled={cancelling} onClick={() => void cancelStartup()}>
            <Square size={16} />
            {cancelling ? "Cancelling startup…" : "Cancel startup"}
          </Button>
        )}
      </div>
    </AuthedLayout>
  )
}

mount(<SpawnPendingPage />)
