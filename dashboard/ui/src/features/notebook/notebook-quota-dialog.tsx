import { useEffect, useState } from "react"

import {
  getGetExperimentQueryKey,
  getGetNotebookQueryKey,
  getListExperimentsQueryKey,
  useStartNotebook,
  useStopNotebook,
} from "@/api/generated/client"
import type { Experiment, StartNotebookRequest } from "@/api/generated/models"
import { formatTime } from "@/shared/format"
import { isNotebookActive } from "@/shared/pod-status"
import { ApiErrorAlert } from "@/shared/ui/api-error-alert"
import {
  Badge,
  Button,
  cn,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Skeleton,
} from "@e-infra/design-system"
import { useQueryClient } from "@tanstack/react-query"
import { CircleCheck, ExternalLink, LoaderCircle, Play, Square, TriangleAlert } from "lucide-react"
import { toast } from "sonner"

import { useNotebookQuota } from "./notebook-hooks"

export type PendingNotebookStart = {
  experimentId: string
  data: StartNotebookRequest
}

type NotebookQuotaDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The notebook start to offer once a slot frees. */
  pendingStart: PendingNotebookStart | null
}

type NotebookQuotaRowProps = {
  experiment: Experiment
  /** Called once the stop request is accepted, so the row survives as "Stopped". */
  onStopped: (experimentId: string) => void
  onError: (error: unknown) => void
}

function NotebookQuotaRow({ experiment, onStopped, onError }: NotebookQuotaRowProps) {
  const notebook = experiment.notebook
  const active = isNotebookActive(notebook?.status)
  const running = notebook?.status === "RUNNING"
  const transitioning = notebook?.status === "TERMINATING" || notebook?.status === "PENDING"

  // Shared with NotebookControls: a RUNNING notebook ticks its uptime every second.
  const [, setTick] = useState(0)
  useEffect(() => {
    if (!running || notebook?.started_at === null || notebook?.started_at === undefined) return
    const id = setInterval(() => setTick((tick) => tick + 1), 1000)
    return () => clearInterval(id)
  }, [running, notebook?.started_at])

  const queryClient = useQueryClient()
  const stop = useStopNotebook({
    mutation: {
      onSuccess: () => {
        toast.success(`Notebook stopping for “${experiment.name}”`)
        onStopped(experiment.id)
        void queryClient.invalidateQueries({ queryKey: getGetNotebookQueryKey(experiment.id) })
        void queryClient.invalidateQueries({ queryKey: getGetExperimentQueryKey(experiment.id) })
        void queryClient.invalidateQueries({ queryKey: getListExperimentsQueryKey() })
      },
      onError,
    },
  })

  const stopping = stop.isPending || notebook?.status === "TERMINATING"
  const uptime =
    running && notebook.started_at !== null
      ? formatTime(Math.max(0, (Date.now() - Date.parse(notebook.started_at)) / 1000))
      : undefined
  const label = !active
    ? "Stopped"
    : notebook?.status === "TERMINATING"
      ? "Stopping…"
      : notebook?.status === "PENDING"
        ? "Starting…"
        : (uptime ?? "…")

  return (
    <li className="flex items-center gap-3 py-3">
      {transitioning ? (
        <LoaderCircle size={12} className="text-text-muted shrink-0 animate-spin" aria-hidden="true" />
      ) : (
        <span
          className={cn("h-2 w-2 shrink-0 rounded-full", running ? "bg-success" : "bg-text-muted/40")}
          aria-hidden="true"
        />
      )}
      <span className={cn("min-w-0 truncate text-sm font-medium", !active && "text-text-muted")}>
        {experiment.name}
      </span>
      <span className="text-text-muted shrink-0 text-sm">{label}</span>
      {active && notebook !== null ? (
        <span className="ml-auto flex shrink-0 gap-2">
          {running && (
            <Button size="icon" aria-label={`Open notebook for ${experiment.name}`} asChild>
              <a href={notebook.path} target="_blank" rel="noopener noreferrer">
                <ExternalLink size={14} aria-hidden="true" />
              </a>
            </Button>
          )}
          {/* UNKNOWN is a K8s hiccup stop can't act on (the API no-ops it). */}
          <Button
            variant="outline"
            size="icon"
            className="border-error text-error hover:bg-error/10"
            aria-label={`Stop notebook for ${experiment.name}`}
            onClick={() => stop.mutate({ experimentId: experiment.id })}
            disabled={stopping || notebook.status === "UNKNOWN"}
          >
            <Square size={14} aria-hidden="true" />
          </Button>
        </span>
      ) : null}
    </li>
  )
}

/**
 * Quota-recovery dialog for a failed or proactively deferred notebook start:
 * lists the running notebooks so one can be stopped, then retries the pending
 * start. Designs beyond the mock's happy path (loading rows, durable action
 * errors, UNKNOWN pods) follow the same visual language.
 */
export function NotebookQuotaDialog({ open, onOpenChange, pendingStart }: NotebookQuotaDialogProps) {
  const queryClient = useQueryClient()
  // Poll while open so a stopping pod flips to "Stopped" without user input.
  const { limit, experiments, runningCount } = useNotebookQuota({ poll: open })
  const [stoppedIds, setStoppedIds] = useState<ReadonlySet<string>>(new Set())
  const [actionError, setActionError] = useState<unknown>(null)

  // Each opening starts a fresh quota session: no stale "Stopped" rows or errors.
  useEffect(() => {
    if (open) {
      setStoppedIds(new Set())
      setActionError(null)
    }
  }, [open])

  const rows = (experiments ?? []).filter(
    (entry) => entry.notebook !== null && (isNotebookActive(entry.notebook.status) || stoppedIds.has(entry.id))
  )
  // The offer unlocks once a slot is provably free; without a known limit, any
  // completed stop is the best signal available. A loading list offers nothing.
  const readyToStart =
    pendingStart !== null &&
    experiments !== undefined &&
    (limit === undefined ? stoppedIds.size > 0 : runningCount !== undefined && runningCount < limit)

  const start = useStartNotebook({
    mutation: {
      onSuccess: (_data, variables) => {
        toast.success("Notebook starting")
        void queryClient.invalidateQueries({ queryKey: getGetNotebookQueryKey(variables.experimentId) })
        void queryClient.invalidateQueries({ queryKey: getGetExperimentQueryKey(variables.experimentId) })
        void queryClient.invalidateQueries({ queryKey: getListExperimentsQueryKey() })
        onOpenChange(false)
      },
      onError: setActionError,
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {readyToStart ? (
              <CircleCheck className="text-success h-5 w-5 shrink-0" aria-hidden="true" />
            ) : (
              <TriangleAlert className="text-warning h-5 w-5 shrink-0" aria-hidden="true" />
            )}
            {readyToStart ? "Ready to start" : "Notebook limit reached"}
          </DialogTitle>
          <DialogDescription>
            Stop one of your notebooks to free a slot. Unsaved work in it will be lost.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <h3 className="text-text-muted flex items-center gap-2 text-sm font-medium tracking-wide uppercase">
            Running notebooks
            <Badge variant="secondary">
              {runningCount === undefined ? "…" : runningCount}/{limit === undefined ? "…" : limit}
            </Badge>
          </h3>
          {experiments === undefined ? (
            <div className="space-y-3 py-1">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : (
            <ul className="divide-border border-border divide-y border-t border-b">
              {rows.map((entry) => (
                <NotebookQuotaRow
                  key={entry.id}
                  experiment={entry}
                  onStopped={(experimentId) => setStoppedIds((current) => new Set(current).add(experimentId))}
                  onError={setActionError}
                />
              ))}
            </ul>
          )}
          {/* Transient failures (stop rejected, retried start still refused) are
              durable UI, matching the app's no-toast-only error rule. */}
          {actionError !== null && <ApiErrorAlert error={actionError} />}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          {pendingStart !== null && (
            <Button
              onClick={() => start.mutate({ experimentId: pendingStart.experimentId, data: pendingStart.data })}
              disabled={!readyToStart || start.isPending}
            >
              <Play aria-hidden="true" />
              {start.isPending ? "Starting…" : "Start new notebook"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
