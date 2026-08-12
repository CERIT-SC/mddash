import { useCallback, useEffect, useMemo, useState } from "react"

import { Button, H1, Muted } from "@e-infra/design-system"
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

  // Both transitions go to spawn-pending: the hub renders spawn_pending or
  // stop_pending there depending on the pending type. Never navigate to the
  // user server URL — the dying proxy would serve errors.
  useEffect(() => {
    if (status === "starting" || status === "stopping") {
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
      <div className="mx-auto flex w-full max-w-lg flex-1 flex-col items-center justify-center gap-6 text-center">
        <div
          aria-hidden="true"
          className={`flex h-16 w-16 items-center justify-center rounded-full ${
            status === "running" ? "bg-success text-success-foreground" : "bg-primary text-primary-foreground"
          }`}
        >
          <Atom size={28} />
        </div>

        <div className="flex flex-col gap-2">
          <H1>
            {status === "running" ? "Your server is running" : null}
            {status === "stopped" ? "Your server is offline" : null}
            {status === "starting" ? "Starting your server…" : null}
            {status === "stopping" ? "Stopping your server…" : null}
          </H1>
          <Muted className="text-base">
            {status === "running" ? "Your personal notebook environment is up." : null}
            {status === "stopped" ? "Your personal notebook server is not running." : null}
            {status === "starting" ? "You will be redirected automatically when it's ready for you." : null}
            {status === "stopping" ? "You can start it again once it has finished stopping." : null}
          </Muted>
        </div>

        {status === "running" ? (
          <>
            <Button size="lg" asChild>
              <a href={serverUrl} className="no-underline">
                <ExternalLink size={16} />
                Open my server
              </a>
            </Button>
            <Button variant="error" size="sm" onClick={stop} disabled={busy}>
              <Square size={16} />
              Stop my server
            </Button>
          </>
        ) : null}

        {status === "stopped" ? (
          <>
            <Button size="lg" onClick={start} disabled={busy}>
              <Play size={16} />
              Start my server
            </Button>
            <Muted>This starts your personal notebook server. It usually takes up to a minute.</Muted>
          </>
        ) : null}
      </div>
    </AuthedLayout>
  )
}

mount(<HomePage />)
