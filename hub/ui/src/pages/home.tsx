import { useCallback, useEffect, useMemo, useState } from "react"

import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, P } from "@e-infra/design-system"
import { ExternalLink, Play, Square } from "lucide-react"
import { toast } from "sonner"

import { AuthedLayout } from "../components/Layouts"
import { HubApi, type HubUserModel } from "../lib/api"
import { getAppConfig } from "../lib/config"
import { mount } from "../lib/mount"

interface HomeConfig {
  /** Template-time snapshot used until the live /api/user response lands. */
  defaultServerActive: boolean
  serverUrl: string
}

type ServerStatus = "stopped" | "starting" | "running" | "stopping"

export function HomePage() {
  const cfg = getAppConfig<HomeConfig>({
    defaultServerActive: false,
    serverUrl: "",
  })
  const api = useMemo(() => new HubApi(cfg.baseUrl, cfg.xsrf), [cfg.baseUrl, cfg.xsrf])

  const [user, setUser] = useState<HubUserModel | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api
      .getUser(cfg.userName)
      .then(setUser)
      .catch(() => toast.error("Could not load server status."))
  }, [api, cfg.userName])

  const server = user?.servers?.[""]
  const status: ServerStatus =
    server?.pending === "spawn"
      ? "starting"
      : server?.pending === "stop"
        ? "stopping"
        : (server?.ready ?? cfg.defaultServerActive)
          ? "running"
          : "stopped"
  const serverUrl = cfg.serverUrl || `${cfg.baseUrl}user/${encodeURIComponent(cfg.userName)}/`

  const start = useCallback(() => {
    setBusy(true)
    api
      .startServer(cfg.userName)
      .then(() => {
        window.location.href = `${cfg.baseUrl}spawn-pending/${encodeURIComponent(cfg.userName)}`
      })
      .catch((e: Error) => {
        toast.error(e.message)
        setBusy(false)
      })
  }, [api, cfg.baseUrl, cfg.userName])

  const stop = useCallback(() => {
    setBusy(true)
    api
      .stopServer(cfg.userName)
      .then(() => {
        window.location.href = `${cfg.baseUrl}stop-pending`
      })
      .catch((e: Error) => {
        toast.error(e.message)
        setBusy(false)
      })
  }, [api, cfg.baseUrl])

  return (
    <AuthedLayout
      baseUrl={cfg.baseUrl}
      userName={cfg.userName}
      adminAccess={cfg.adminAccess}
      logoutUrl={cfg.logoutUrl}
      current="home"
      announcement={cfg.announcement}
    >
      <Card className="mx-auto w-full max-w-xl">
        <CardHeader>
          <CardTitle>My server</CardTitle>
          <CardDescription>Launch or stop your personal computing pod</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <P className="mb-0">Status:</P>
            {status === "running" ? <Badge className="bg-success text-success-foreground">Running</Badge> : null}
            {status === "starting" ? <Badge variant="secondary">Starting…</Badge> : null}
            {status === "stopping" ? <Badge variant="secondary">Stopping…</Badge> : null}
            {status === "stopped" ? <Badge variant="secondary">Stopped</Badge> : null}
          </div>

          {status === "running" ? (
            <>
              <Button size="lg" asChild>
                <a href={serverUrl} className="no-underline">
                  <ExternalLink size={16} />
                  Open my server
                </a>
              </Button>
              <Button size="lg" variant="error" onClick={stop} disabled={busy}>
                <Square size={16} />
                Stop my server
              </Button>
            </>
          ) : null}

          {status === "starting" ? (
            <Button size="lg" variant="secondary" asChild>
              <a href={`${cfg.baseUrl}spawn-pending/${encodeURIComponent(cfg.userName)}`} className="no-underline">
                Watch startup progress
              </a>
            </Button>
          ) : null}

          {status === "stopping" ? (
            <Button size="lg" variant="secondary" asChild>
              <a href={`${cfg.baseUrl}stop-pending`} className="no-underline">
                Watch shutdown progress
              </a>
            </Button>
          ) : null}

          {status === "stopped" ? (
            <Button size="lg" onClick={start} disabled={busy}>
              <Play size={16} />
              Start my server
            </Button>
          ) : null}
        </CardContent>
      </Card>
    </AuthedLayout>
  )
}

mount(<HomePage />)
