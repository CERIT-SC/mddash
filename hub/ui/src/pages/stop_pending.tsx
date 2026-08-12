import { useEffect, useMemo, useState } from "react"

import { Button, H1, Muted } from "@e-infra/design-system"
import { Atom, Clock, RefreshCw } from "lucide-react"

import { AuthedLayout } from "../components/Layouts"
import { HubApi } from "../lib/api"
import { getAppConfig } from "../lib/config"
import { mount } from "../lib/mount"

export function StopPendingPage() {
  const cfg = getAppConfig({})
  const api = useMemo(() => new HubApi(cfg.baseUrl, cfg.xsrf), [cfg.baseUrl, cfg.xsrf])
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => {
      setElapsed((s) => s + 2)
      api
        .getUser(cfg.userName)
        .then((user) => {
          if (!user.pending && !(user.servers?.[""]?.active ?? false)) {
            clearInterval(timer)
            window.location.href = `${cfg.baseUrl}home`
          }
        })
        .catch(() => {
          /* transient API errors — keep polling */
        })
    }, 2000)
    return () => clearInterval(timer)
  }, [api, cfg.baseUrl, cfg.userName])

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
          className="bg-primary text-primary-foreground flex h-16 w-16 items-center justify-center rounded-full"
        >
          <Atom size={28} />
        </div>

        <div className="flex flex-col gap-2">
          <H1>Stopping your server…</H1>
          <Muted className="text-base">You can start it again once it has finished stopping.</Muted>
        </div>

        <div className="flex items-center gap-1">
          <Clock size={14} aria-hidden="true" className="text-text-muted" />
          <Muted>This usually takes a few seconds</Muted>
        </div>

        {elapsed >= 30 ? (
          <Button variant="secondary" size="sm" onClick={() => window.location.reload()}>
            <RefreshCw size={16} />
            Refresh
          </Button>
        ) : null}
      </div>
    </AuthedLayout>
  )
}

mount(<StopPendingPage />)
