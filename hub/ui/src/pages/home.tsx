import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { Button, H1, Lead, Muted } from "@e-infra/design-system"
import { Atom, ExternalLink, Play, Square } from "lucide-react"
import { toast } from "sonner"

import { HeroHeading, PageHero, PipelineSteps, START_HINT, StatusIcon } from "../components/Hero"
import { AuthedLayout } from "../components/Layouts"
import { HubApi, type HubUserModel } from "../lib/api"
import { getAppConfig } from "../lib/config"
import { mount } from "../lib/mount"
import { serverStatus, type ServerStatus } from "../lib/status"

type Transition = Extract<ServerStatus, "starting" | "stopping">

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
  // In-flight transition feedback; renders the transition copy without driving the redirect.
  const [requested, setRequested] = useState<Transition | null>(null)
  // Set when the transition POST resolves; feeds the redirect effect. refresh never clears it:
  // a getUser issued before that POST returns stale state and would strand the page.
  const [optimistic, setOptimistic] = useState<Transition | null>(null)

  const refresh = useCallback(() => {
    return api
      .getUser(cfg.userName)
      .then((u) => setUser(u))
      .catch(() => toast.error("Could not load server status."))
  }, [api, cfg.userName])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const server = user?.servers?.[""]
  const liveStatus: ServerStatus = user ? serverStatus(server) : cfg.defaultServerActive ? "running" : "stopped"
  const status = optimistic ?? liveStatus
  const shown = requested ?? status
  const serverUrl = cfg.serverUrl || `${cfg.baseUrl}user/${encodeURIComponent(cfg.userName)}/`

  // Route both transitions to spawn-pending (the hub picks the pending template);
  // never the user server URL. The dying proxy serves errors.
  useEffect(() => {
    if (status === "starting" || status === "stopping") {
      window.location.href = `${cfg.baseUrl}spawn-pending/${encodeURIComponent(cfg.userName)}`
    }
  }, [status, cfg.baseUrl, cfg.userName])

  // Redirect only after the hub has registered the transition: navigating
  // earlier can abort the POST or make spawn-pending render not_running.
  const start = useCallback(() => {
    setRequested("starting")
    api
      .startServer(cfg.userName)
      .then(() => setOptimistic("starting"))
      .catch((e: Error) => {
        toast.error(e.message)
        setRequested(null)
      })
  }, [api, cfg.userName])

  const stop = useCallback(() => {
    setRequested("stopping")
    api
      .stopServer(cfg.userName)
      .then(() => setOptimistic("stopping"))
      .catch((e: Error) => {
        toast.error(e.message)
        setRequested(null)
      })
  }, [api, cfg.userName])

  // bfcache restores this page verbatim on Back: reset transition state and
  // re-fetch, or the page is stuck showing the transition forever.
  useEffect(() => {
    const onPageShow = (e: PageTransitionEvent) => {
      if (!e.persisted) return
      setRequested(null)
      setOptimistic(null)
      void refresh()
    }
    window.addEventListener("pageshow", onPageShow)
    return () => window.removeEventListener("pageshow", onPageShow)
  }, [refresh])

  // Dashboard "Stop server" lands here with ?stop: hub pages own the stop call
  // (the dashboard can't reach the hub API. The _xsrf cookie is scoped to /hub),
  // and the stopping transition below routes to spawn-pending like a manual stop.
  const stopRequested = useRef(new URLSearchParams(window.location.search).has("stop"))

  useEffect(() => {
    if (stopRequested.current && status === "running") {
      stopRequested.current = false
      stop()
    }
  }, [status, stop])

  return (
    <AuthedLayout
      baseUrl={cfg.baseUrl}
      userName={cfg.userName}
      adminAccess={cfg.adminAccess}
      logoutUrl={cfg.logoutUrl}
      current="home"
      announcement={cfg.announcement}
    >
      <PageHero>
        <StatusIcon tone={shown === "running" ? "success" : "primary"} icon={Atom} />

        <HeroHeading>
          <H1>
            {shown === "running" ? "Your server is running" : null}
            {shown === "stopped" ? "A Virtual Research Environment for Molecular Dynamics" : null}
            {shown === "starting" ? "Starting your server…" : null}
            {shown === "stopping" ? "Stopping your server…" : null}
          </H1>
          {shown === "stopped" ? (
            <Lead className="mx-auto max-w-md">
              MDDash lets you prepare, tune, run, analyze, and publish MD simulations — all in the browser, without
              touching the command line.
            </Lead>
          ) : (
            <Muted className="text-base">
              {shown === "running" ? "Your personal notebook environment is up." : null}
              {shown === "starting" ? "You will be redirected automatically when it's ready for you." : null}
              {shown === "stopping" ? "You can start it again once it has finished stopping." : null}
            </Muted>
          )}
        </HeroHeading>

        {shown === "running" ? (
          <>
            <Button size="lg" asChild>
              <a href={serverUrl} className="no-underline">
                <ExternalLink size={16} />
                Open my server
              </a>
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="border-error text-error hover:bg-error/10"
              onClick={stop}
              disabled={requested !== null}
            >
              <Square fill="currentColor" size={16} />
              Stop my server
            </Button>
          </>
        ) : null}

        {shown === "stopped" ? (
          <>
            <PipelineSteps />
            <Button size="lg" onClick={start} disabled={requested !== null}>
              <Play size={16} />
              Start my server
            </Button>
            <Muted>{START_HINT}</Muted>
          </>
        ) : null}
      </PageHero>
    </AuthedLayout>
  )
}

mount(<HomePage />)
