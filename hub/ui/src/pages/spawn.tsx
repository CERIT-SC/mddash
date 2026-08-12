import { useEffect, useRef, useState } from "react"

import {
  Alert,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  H1,
  Lead,
  Muted,
  Separator,
} from "@e-infra/design-system"
import { Atom, LoaderCircle, Play, RefreshCw, TriangleAlert } from "lucide-react"

import { DetailsLog, FAILED_LEAD, HeroHeading, LogEntry, PageHero, StatusIcon, SupportNote } from "../components/Hero"
import { AuthedLayout } from "../components/Layouts"
import { HubApi } from "../lib/api"
import { DEV_FALLBACK_BASE_URL, getAppConfig } from "../lib/config"
import { mount } from "../lib/mount"

interface SpawnConfig {
  /** Form POST target (used only when an options form exists). */
  url: string
  errorMessage: string | null
  errorHtmlMessage: string | null
  /** Server-rendered options form HTML; empty means MDDash's fixed pod. */
  optionsForm: string
}

export function SpawnPage() {
  const cfg = getAppConfig<SpawnConfig>({
    url: `${DEV_FALLBACK_BASE_URL}spawn`,
    errorMessage: null,
    errorHtmlMessage: null,
    optionsForm: "",
  })

  // A hub-rendered spawn error means the spawn already failed — show the failed
  // state instead of auto-retrying (which would silently loop).
  const hasHubError = Boolean(cfg.errorHtmlMessage || cfg.errorMessage)
  const [status, setStatus] = useState<"starting" | "failed">(hasHubError ? "failed" : "starting")
  const [error, setError] = useState<string | null>(null)
  const started = useRef(false)

  useEffect(() => {
    if (cfg.optionsForm || hasHubError) return
    // React StrictMode double-invokes effects — guard against spawning twice.
    if (started.current) return
    started.current = true
    const api = new HubApi(cfg.baseUrl, cfg.xsrf)
    api
      .startServer(cfg.userName)
      .then(() => {
        window.location.href = `${cfg.baseUrl}spawn-pending/${encodeURIComponent(cfg.userName)}`
      })
      .catch((e: Error) => {
        setStatus("failed")
        setError(e.message)
      })
  }, [cfg, hasHubError])

  const errorHtml = cfg.errorHtmlMessage
  const errorText = cfg.errorMessage

  if (cfg.optionsForm) {
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
            <CardTitle>Server options</CardTitle>
          </CardHeader>
          <CardContent>
            {errorText ? (
              <Alert variant="error" className="mb-4">
                Error: {errorText}
              </Alert>
            ) : null}
            {errorHtml ? (
              <Alert variant="error" className="mb-4" dangerouslySetInnerHTML={{ __html: errorHtml }} />
            ) : null}
            <form
              method="post"
              encType="multipart/form-data"
              action={cfg.url}
              className="flex flex-col gap-4"
              onSubmit={(e) => {
                const input = e.currentTarget.querySelector("button[type=submit]")
                if (input) input.setAttribute("disabled", "")
              }}
            >
              {/* Options form rendered by the spawner (trusted hub output). */}
              <div dangerouslySetInnerHTML={{ __html: cfg.optionsForm }} />
              <Button type="submit" size="lg">
                <Play size={16} />
                Start
              </Button>
            </form>
          </CardContent>
        </Card>
      </AuthedLayout>
    )
  }

  const failed = status === "failed"

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
          <H1>{failed ? "Failed to start your server" : "Starting your server"}</H1>
          {failed ? (
            <Lead>{FAILED_LEAD}</Lead>
          ) : (
            <Muted className="text-base">You will be redirected to the progress page in a moment.</Muted>
          )}
        </HeroHeading>

        {failed ? (
          <>
            <Button size="lg" onClick={() => window.location.reload()}>
              <RefreshCw size={16} />
              Try again
            </Button>
            <SupportNote />
            <Separator className="w-full" />
            <DetailsLog open summary="Event log">
              {errorHtml ? (
                <LogEntry html={errorHtml} />
              ) : (errorText ?? error) ? (
                <LogEntry>{errorText ?? error}</LogEntry>
              ) : (
                <LogEntry>No failure details available.</LogEntry>
              )}
            </DetailsLog>
          </>
        ) : (
          <LoaderCircle className="text-primary animate-spin" size={32} aria-hidden="true" />
        )}
      </PageHero>
    </AuthedLayout>
  )
}

mount(<SpawnPage />)
