import { useEffect, useState } from "react"

import { toApiError } from "@/api/errors"
import {
  getGetExperimentQueryKey,
  getGetNotebookQueryKey,
  getListExperimentsQueryKey,
  useGetNotebook,
  useStopNotebook,
} from "@/api/generated/client"
import { formatTime } from "@/shared/format"
import { isNotebookActive } from "@/shared/pod-status"
import { Button, cn } from "@e-infra/design-system"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { ExternalLink, LoaderCircle, Square } from "lucide-react"
import { toast } from "sonner"

// Transitioning pods get a fast poll so the bar follows them closely; steady
// state needs only an occasional check (idle-culling, starts from the dashboard).
const TRANSITION_POLL_MS = 3000
const STEADY_POLL_MS = 30_000
// Serving probes back off to a 30s ceiling (no hard give-up — slow binder
// installs take minutes); enough failures degrade the label below.
const PROBE_MAX_DELAY_MS = 30_000
const SLOW_PROBE_FAILURES = 8
const TRANSITIONING = new Set<string>(["PENDING", "TERMINATING"])

type NotebookStatusBarProps = { experimentId: string }

export function NotebookStatusBar({ experimentId }: NotebookStatusBarProps) {
  const queryClient = useQueryClient()
  // Forces a re-render every second so the uptime readout ticks between refetches.
  const [, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((tick) => tick + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const notebookQuery = useGetNotebook(experimentId, {
    query: {
      retry: false,
      refetchInterval: (query) => {
        const data = query.state.data?.status === 200 ? query.state.data.data : undefined
        return data !== undefined && TRANSITIONING.has(data.status) ? TRANSITION_POLL_MS : STEADY_POLL_MS
      },
    },
  })

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: getGetNotebookQueryKey(experimentId) })
    void queryClient.invalidateQueries({ queryKey: getGetExperimentQueryKey(experimentId) })
    void queryClient.invalidateQueries({ queryKey: getListExperimentsQueryKey() })
  }

  const stop = useStopNotebook({
    mutation: {
      onSuccess: () => {
        toast.success("Notebook stopping")
        invalidate()
      },
      onError: (error) => toast.error(toApiError(error).message),
    },
  })

  const notebook = notebookQuery.data?.status === 200 ? notebookQuery.data.data : undefined
  const running = notebook?.status === "RUNNING"

  // RUNNING only means the container started — Jupyter (or a binder env install)
  // lags behind, and the proxy 502s until it serves. started_at in the key re-probes restarts.
  const sessionKey = running ? `${experimentId}:${notebook.started_at ?? ""}` : null
  const probe = useQuery({
    queryKey: ["notebook-probe", sessionKey],
    enabled: sessionKey !== null,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: 0,
    retry: Number.POSITIVE_INFINITY,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, PROBE_MAX_DELAY_MS),
    queryFn: async () => {
      // enabled implies RUNNING, so notebook and its path are defined here.
      const response = await fetch(notebook!.path, { credentials: "same-origin" })
      if (!response.ok) throw new Error(`Notebook not ready (${response.status})`)
      return true
    },
  })
  const ready = probe.data === true

  // The bar exists only while the notebook is up; loading, errors, and
  // DOWN/ERROR leave the slot empty (start lives on the dashboard card).
  if (notebook === undefined || !isNotebookActive(notebook.status)) return null

  const stopping = stop.isPending || notebook.status === "TERMINATING"
  const starting = notebook.status === "PENDING" || (running && !ready)
  const spinning = starting || stopping
  const uptime =
    notebook.started_at !== null ? Math.max(0, (Date.now() - Date.parse(notebook.started_at)) / 1000) : undefined

  // Startup phases spin with Stop still available (a slow or stuck start must be
  // cancellable); Open appears only once the notebook actually serves.
  const label = stopping
    ? "Stopping…"
    : notebook.status === "PENDING"
      ? "Starting…"
      : running && !ready
        ? probe.failureCount >= SLOW_PROBE_FAILURES
          ? "Taking longer than expected"
          : "Initializing…"
        : running && uptime !== undefined
          ? formatTime(uptime)
          : "…"

  return (
    <section
      aria-label="Notebook status"
      className="border-border bg-surface mx-auto flex w-fit max-w-full flex-wrap items-center gap-x-6 gap-y-2 rounded-b-lg border border-t-0 px-4 py-2 shadow-md md:px-6"
    >
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
            <a href={notebook.path} target="_blank" rel="noopener noreferrer" className="no-underline">
              <ExternalLink size={14} />
              Open
            </a>
          </Button>
        )}
        {/* Red-bordered ghost of the mock via DS outline variant + error tokens. */}
        <Button
          variant="outline"
          size="sm"
          className="border-error-400 text-error hover:bg-error-50"
          onClick={() => stop.mutate({ experimentId })}
          // UNKNOWN is a K8s hiccup, not a state stop can act on (the API no-ops it).
          disabled={stopping || notebook.status === "UNKNOWN"}
        >
          <Square size={14} />
          {stopping ? "Stopping…" : "Stop notebook"}
        </Button>
      </div>
    </section>
  )
}
