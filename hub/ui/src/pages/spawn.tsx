import { useEffect, useRef, useState } from "react"

import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  P,
} from "@e-infra/design-system"
import { LoaderCircle, Play, TriangleAlert } from "lucide-react"

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

  const [status, setStatus] = useState<"starting" | "failed">("starting")
  const [error, setError] = useState<string | null>(null)
  const started = useRef(false)

  useEffect(() => {
    if (cfg.optionsForm) return
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
  }, [cfg])

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
          <CardTitle>Starting your server</CardTitle>
          <CardDescription>You'll be redirected to the progress page in a moment</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col items-center gap-4 py-6">
          {status === "starting" ? (
            <>
              <LoaderCircle className="text-primary animate-spin" size={32} />
              <P>Requesting your server…</P>
            </>
          ) : (
            <>
              <Alert variant="error" className="w-full">
                <AlertTitle className="flex items-center gap-2">
                  <TriangleAlert size={16} />
                  Spawn failed
                </AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
              <Button variant="secondary" onClick={() => window.location.reload()}>
                Try again
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </AuthedLayout>
  )
}

mount(<SpawnPage />)
