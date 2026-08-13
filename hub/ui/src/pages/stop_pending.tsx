import { useEffect, useMemo, useState } from "react"

import { Button, H1, Muted } from "@e-infra/design-system"
import { Atom, RefreshCw } from "lucide-react"

import { HeroHeading, PageHero, StatusIcon, WaitHint } from "../components/Hero"
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
      <PageHero>
        <StatusIcon tone="primary" icon={Atom} />

        <HeroHeading>
          <H1>Stopping your server…</H1>
          <Muted className="text-base">You can start it again once it has finished stopping.</Muted>
        </HeroHeading>

        <WaitHint>This usually takes a few seconds</WaitHint>

        {elapsed >= 30 ? (
          <Button variant="secondary" size="sm" onClick={() => window.location.reload()}>
            <RefreshCw size={16} />
            Refresh
          </Button>
        ) : null}
      </PageHero>
    </AuthedLayout>
  )
}

mount(<StopPendingPage />)
