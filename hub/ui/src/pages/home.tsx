import { useCallback, useEffect, useMemo, useState } from "react"

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  H1,
  Muted,
  P,
} from "@e-infra/design-system"
import { Atom, ExternalLink, Play, Square } from "lucide-react"
import { toast } from "sonner"

import { AuthedLayout } from "../components/Layouts"
import { HubApi, type HubUserModel } from "../lib/api"
import { getAppConfig } from "../lib/config"
import { mount } from "../lib/mount"
import { serverStatus, type ServerStatus } from "../lib/status"

interface HomeConfig {
  /** Template-time snapshot used until the live /api/user response lands. */
  defaultServerActive: boolean
  serverUrl: string
}

export function HomePage() {
  const cfg = getAppConfig<HomeConfig>({
    defaultServerActive: false,
    serverUrl: "",
  })
  const api = useMemo(() => new HubApi(cfg.baseUrl, cfg.xsrf), [cfg.baseUrl, cfg.xsrf])

  const [user, setUser] = useState<HubUserModel | null>(null)
  const [busy, setBusy] = useState(false)
  const [optimistic, setOptimistic] = useState<ServerStatus | null>(null)

  const refresh = useCallback(() => {
    return api
      .getUser(cfg.userName)
      .then((u) => {
        setUser(u)
        setOptimistic(null)
      })
      .catch(() => toast.error("Could not load server status."))
  }, [api, cfg.userName])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const server = user?.servers?.[""]
  const liveStatus: ServerStatus = user ? serverStatus(server) : cfg.defaultServerActive ? "running" : "stopped"
  const status = optimistic ?? liveStatus
  const serverUrl = cfg.serverUrl || `${cfg.baseUrl}user/${encodeURIComponent(cfg.userName)}/`

  // While stopping, the hub itself serves stop_pending on the server route — no redirect needed here.
  useEffect(() => {
    if (status === "starting") {
      window.location.href = `${cfg.baseUrl}spawn-pending/${encodeURIComponent(cfg.userName)}`
    }
  }, [status, cfg.baseUrl, cfg.userName])

  const start = useCallback(() => {
    setBusy(true)
    setOptimistic("starting")
    api.startServer(cfg.userName).catch((e: Error) => {
      toast.error(e.message)
      setOptimistic(null)
      setBusy(false)
    })
  }, [api, cfg.userName])

  const stop = useCallback(() => {
    setBusy(true)
    setOptimistic("stopping")
    api.stopServer(cfg.userName).catch((e: Error) => {
      toast.error(e.message)
      setOptimistic(null)
      setBusy(false)
    })
  }, [api])

  return (
    <AuthedLayout
      baseUrl={cfg.baseUrl}
      userName={cfg.userName}
      adminAccess={cfg.adminAccess}
      logoutUrl={cfg.logoutUrl}
      current="home"
      announcement={cfg.announcement}
    >
      {status === "stopped" ? (
        <div className="mx-auto flex w-full max-w-lg flex-1 flex-col items-center justify-center gap-6 text-center">
          <div
            aria-hidden="true"
            className="bg-primary text-primary-foreground flex h-16 w-16 items-center justify-center rounded-full"
          >
            <Atom size={28} />
          </div>

          <div className="flex flex-col gap-2">
            <H1>Your server is offline</H1>
            <Muted className="text-base">Your personal notebook server is not running.</Muted>
          </div>

          <Button size="lg" onClick={start} disabled={busy}>
            <Play size={16} />
            Start my server
          </Button>

          <Muted>This starts your personal notebook server. It usually takes up to a minute.</Muted>
        </div>
      ) : (
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
          </CardContent>
        </Card>
      )}
    </AuthedLayout>
  )
}

mount(<HomePage />)
