import { useEffect, useMemo, useState } from "react"

import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Progress,
} from "@e-infra/design-system"
import { LoaderCircle, RotateCw, Square, TriangleAlert } from "lucide-react"

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
            {status === "failed" ? (
              <TriangleAlert className="text-error" size={20} />
            ) : (
              <LoaderCircle className="text-primary animate-spin" size={20} />
            )}
            {status === "failed" ? "Server failed to start" : "Your server is starting up"}
          </CardTitle>
          <CardDescription>
            {status === "failed"
              ? "The server could not be started. Try starting it again."
              : "You will be redirected automatically when it is ready"}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {status !== "failed" ? (
            <>
              {streamEnded ? null : <Progress value={progress} />}
              <p className="text-text-muted text-sm" aria-live="polite">
                {streamEnded ? "Waiting for server to become ready…" : (currentMessage ?? "Contacting the spawner…")}
              </p>
              {cancelError ? <Alert variant="error">{cancelError}</Alert> : null}
              <Button variant="error" disabled={cancelling} onClick={() => void cancelStartup()}>
                <Square size={16} />
                {cancelling ? "Cancelling startup…" : "Cancel startup"}
              </Button>
            </>
          ) : null}
          {status === "failed" ? (
            <Alert variant="error" className="flex items-start gap-2">
              <TriangleAlert size={16} />
              <span>
                The server failed to start.{currentMessage ? ` ${currentMessage}` : ""}
                {retryError ? ` ${retryError}` : ""}
              </span>
            </Alert>
          ) : null}
          <details open={status === "failed"} className="bg-surface rounded-md p-3">
            <summary className="text-text-muted cursor-pointer text-sm">Event log</summary>
            <div className="mt-2 flex flex-col gap-1">
              {log.length === 0 ? (
                <span className="text-text-muted text-xs">No events yet.</span>
              ) : (
                log.map((entry, i) =>
                  entry.html ? (
                    <span
                      key={i}
                      className="text-text-muted text-xs"
                      dangerouslySetInnerHTML={{ __html: entry.html }}
                    />
                  ) : (
                    <span key={i} className="text-text-muted text-xs">
                      {entry.text}
                    </span>
                  )
                )
              )}
            </div>
          </details>
          {status === "failed" ? (
            <Button variant="secondary" disabled={retrying} onClick={() => void retry()}>
              <RotateCw className={retrying ? "animate-spin" : undefined} size={16} />
              {retrying ? "Retrying…" : "Retry starting server"}
            </Button>
          ) : null}
        </CardContent>
      </Card>
    </AuthedLayout>
  )
}

mount(<SpawnPendingPage />)
