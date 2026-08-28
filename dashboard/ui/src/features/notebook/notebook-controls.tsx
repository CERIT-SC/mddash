import { useEffect, useState } from "react"

import { toApiError } from "@/api/errors"
import { useStopNotebook } from "@/api/generated/client"
import type { Notebook } from "@/api/generated/models"
import { formatTime } from "@/shared/format"
import { Button, cn } from "@e-infra/design-system"
import { ExternalLink, LoaderCircle, Square } from "lucide-react"
import { toast } from "sonner"

import { useNotebookInvalidation } from "./notebook-hooks"

// Probe failures past this degrade the label to "Taking longer than expected".
const SLOW_PROBE_FAILURES = 8

type NotebookControlsProps = {
  experimentId: string
  /** An ACTIVE notebook (PENDING/RUNNING/UNKNOWN/TERMINATING); sites hide the controls otherwise. */
  notebook: Notebook
  ready: boolean
  probeFailures: number
  /** Open target; defaults to the (token-embedded) lab root. */
  openHref?: string
  className?: string
}

/** Active-notebook row shared by the top bar and Setup launcher; Stop stays
    available throughout — a slow or stuck start must be cancellable. */
export function NotebookControls({
  experimentId,
  notebook,
  ready,
  probeFailures,
  openHref,
  className,
}: NotebookControlsProps) {
  const invalidate = useNotebookInvalidation(experimentId)
  const ticking = notebook.status === "RUNNING" && ready && notebook.started_at !== null
  const [, setTick] = useState(0)
  useEffect(() => {
    if (!ticking) return
    const id = setInterval(() => setTick((tick) => tick + 1), 1000)
    return () => clearInterval(id)
  }, [ticking])

  const stop = useStopNotebook({
    mutation: {
      onSuccess: () => {
        toast.success("Notebook stopping")
        invalidate()
      },
      onError: (error) => toast.error(toApiError(error).message),
    },
  })

  const running = notebook.status === "RUNNING"
  const stopping = stop.isPending || notebook.status === "TERMINATING"
  const starting = notebook.status === "PENDING" || (running && !ready)
  const spinning = starting || stopping
  const uptime =
    notebook.started_at !== null ? Math.max(0, (Date.now() - Date.parse(notebook.started_at)) / 1000) : undefined

  const label = stopping
    ? "Stopping…"
    : notebook.status === "PENDING"
      ? "Starting…"
      : running && !ready
        ? probeFailures >= SLOW_PROBE_FAILURES
          ? "Taking longer than expected"
          : "Initializing…"
        : running && uptime !== undefined
          ? formatTime(uptime)
          : "…"

  return (
    <div className={cn("flex w-fit max-w-full flex-wrap items-center gap-x-6 gap-y-2 px-3 py-2", className)}>
      <div className="flex items-center gap-3 text-sm">
        {spinning ? (
          <LoaderCircle size={12} className="text-text-muted animate-spin" aria-hidden="true" />
        ) : (
          <span
            className={cn("h-2 w-2 rounded-full", running ? "bg-success" : "bg-text-muted/40")}
            aria-hidden="true"
          />
        )}
        <span className="font-medium">Notebook</span>
        <span className="text-text-muted">{label}</span>
      </div>
      <div className="flex items-center gap-2">
        {running && ready && (
          // notebook.path already embeds the access token.
          <Button size="sm" asChild>
            <a href={openHref ?? notebook.path} target="_blank" rel="noopener noreferrer" className="no-underline">
              <ExternalLink size={14} />
              Open notebook
            </a>
          </Button>
        )}
        {/* UNKNOWN is a K8s hiccup stop can't act on (the API no-ops it). */}
        <Button
          variant="outline"
          size="sm"
          className="border-error text-error hover:bg-error/10"
          onClick={() => stop.mutate({ experimentId })}
          disabled={stopping || notebook.status === "UNKNOWN"}
        >
          <Square size={14} />
          {stopping ? "Stopping…" : "Stop notebook"}
        </Button>
      </div>
    </div>
  )
}
