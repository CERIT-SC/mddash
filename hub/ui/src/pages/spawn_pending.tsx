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
import { LoaderCircle, TriangleAlert } from "lucide-react"

import { AuthedLayout } from "../components/Layouts"
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
  const { progress, currentMessage, log, status } = useSpawnProgress(cfg.progressUrl)

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
            <LoaderCircle className="text-primary animate-spin" size={20} />
            Your server is starting up
          </CardTitle>
          <CardDescription>You will be redirected automatically when it is ready</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Progress value={progress} />
          <p className="text-text-muted text-sm" aria-live="polite">
            {currentMessage ?? "Contacting the spawner…"}
          </p>
          {status === "reconnecting" ? <p className="text-text-muted text-xs">Connection lost — retrying…</p> : null}
          {status === "lost" ? (
            <Alert variant="warning">Lost contact with the hub. Your server may still be starting.</Alert>
          ) : null}
          {status === "failed" ? (
            <Alert variant="error" className="flex items-start gap-2">
              <TriangleAlert size={16} />
              The server failed to start. See the event log below for details.
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
          {status === "failed" || status === "lost" ? (
            <Button variant="secondary" onClick={() => window.location.reload()}>
              Retry
            </Button>
          ) : null}
        </CardContent>
      </Card>
    </AuthedLayout>
  )
}

mount(<SpawnPendingPage />)
