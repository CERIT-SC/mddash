import { useEffect, useState } from "react"

import { useGetMetrics } from "@/api/generated/client"
import { formatBytes, formatTime } from "@/shared/format"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
  buttonVariants,
  Progress,
  Separator,
} from "@e-infra/design-system"
import { Square, X } from "lucide-react"

// The hub's _xsrf cookie is path-scoped to /hub, so this page can neither read
// it nor call the hub API. The hub home page owns the stop call (Jinja-rendered
// token) and honors ?stop; it routes through spawn-pending → stop_pending.html,
// which survives the user pod dying mid-transition (unlike any /user/ URL).
const HUB_STOP_URL = "/hub/home?stop"

export function ServerStatusBar() {
  const metrics = useGetMetrics({ query: { retry: false } })
  const [confirmStop, setConfirmStop] = useState(false)
  const [stopping, setStopping] = useState(false)
  // Forces a re-render every second so the uptime readout ticks between refetches.
  const [, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((tick) => tick + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const data = metrics.data?.status === 200 ? metrics.data.data : undefined
  const used = data?.storage_used_bytes ?? undefined
  const limit = data?.storage_limit_bytes ?? undefined
  const hasStorage = used !== undefined && limit !== undefined && limit > 0
  const percent = hasStorage ? Math.min(100, Math.round(((used ?? 0) / (limit ?? 1)) * 100)) : 0
  const uptime =
    data?.uptime_seconds !== undefined ? data.uptime_seconds + (Date.now() - metrics.dataUpdatedAt) / 1000 : undefined

  function onStop() {
    setStopping(true)
    location.assign(HUB_STOP_URL)
  }

  return (
    <section
      aria-label="Server status"
      className="border-border bg-surface mx-auto flex w-fit max-w-full flex-wrap items-center gap-x-6 gap-y-2 rounded-b-lg border border-t-0 px-4 py-2 shadow-md md:px-6"
    >
      <div className="flex items-center gap-3 text-sm">
        <span className="bg-success h-2 w-2 rounded-full" aria-hidden="true" />
        <span className="font-medium">Server</span>
        <span className="text-text-muted">{uptime === undefined ? "…" : formatTime(uptime)}</span>
      </div>
      <Separator orientation="vertical" className="hidden h-6 sm:block" />
      <div className="flex flex-col gap-1 text-sm">
        <span className="flex items-baseline gap-3">
          <span className="text-text-muted">Storage</span>
          {metrics.isLoading ? (
            <span className="text-text-muted">…</span>
          ) : hasStorage ? (
            <span>
              <span className="font-medium">{formatBytes(used ?? 0)}</span>
              <span className="text-text-muted">{` / ${formatBytes(limit ?? 0)}`}</span>
            </span>
          ) : (
            <span className="text-text-muted">N/A</span>
          )}
        </span>
        {hasStorage && <Progress value={percent} className="w-full" aria-label="Storage usage" />}
      </div>
      <Separator orientation="vertical" className="hidden h-6 sm:block" />
      <div>
        {/* Red-bordered ghost of the mock via DS outline variant + error tokens. */}
        <Button
          variant="outline"
          size="sm"
          className="border-error text-error hover:bg-error/10"
          onClick={() => setConfirmStop(true)}
          disabled={stopping}
        >
          <Square size={14} />
          {stopping ? "Stopping…" : "Stop server"}
        </Button>
      </div>

      {/* One click must not kill the server and its in-memory kernel state —
          every destructive action in the app confirms first. */}
      <AlertDialog open={confirmStop} onOpenChange={setConfirmStop}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <X className="text-error" aria-hidden />
              Stop server
            </AlertDialogTitle>
            <AlertDialogDescription>
              Stop this server? Any unsaved notebook state will be lost; the server can be started again from the
              server's home page.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep running</AlertDialogCancel>
            <AlertDialogAction className={buttonVariants({ variant: "error" })} onClick={onStop}>
              Stop server
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  )
}
