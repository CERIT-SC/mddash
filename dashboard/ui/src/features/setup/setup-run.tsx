import { useEffect, useRef, useState } from "react"

import {
  getGetSetupQueryKey,
  getListSimulationsQueryKey,
  useGetNotebookConfig,
  useGetSetup,
  useStartSetup,
  useStopSetup,
} from "@/api/generated/client"
import type { SetupRun, StartSetupRequestTier } from "@/api/generated/models"
import { ApiErrorAlert } from "@/shared/ui/api-error-alert"
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Checkbox,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Label,
  Progress,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
} from "@e-infra/design-system"
import { useQueryClient } from "@tanstack/react-query"
import { LoaderCircle, Play, Square } from "lucide-react"

const SETUP_POLL_MS = 3000

const isLive = (run: SetupRun | undefined) => run?.state === "starting" || run?.state === "running"

/** "Step 4 of 11 · Solvate", or as much of it as the run knows. */
function stepLabel(run: SetupRun, step = run.step ?? 0): string {
  const position = run.total ? `Step ${step} of ${run.total}` : `Step ${step}`
  return run.title ? `${position} · ${run.title}` : position
}

type SetupRunPanelProps = {
  experimentId: string
  /** Experiment-relative setup notebook. */
  notebook: string
  /** Why Run setup is unavailable (a run would overwrite a manifest in use); undefined when it can run. */
  blockedReason: string | undefined
  /** Opens the notebook view, where the user edits, fixes, or watches it. */
  onOpenNotebook: () => void
}

/** Setup card's default view: run the setup notebook headless and follow its progress. */
export function SetupRunPanel({ experimentId, notebook, blockedReason, onOpenNotebook }: SetupRunPanelProps) {
  const queryClient = useQueryClient()
  const [expertOpen, setExpertOpen] = useState(false)
  const params = { notebook }
  const query = useGetSetup(experimentId, params, {
    query: {
      retry: false,
      refetchInterval: (q) => {
        const data = q.state.data as { status: number; data: SetupRun } | undefined
        return data?.status === 200 && isLive(data.data) ? SETUP_POLL_MS : false
      },
    },
  })
  const missing = (query.error as { status?: number } | null)?.status === 404
  const run = !missing && query.data?.status === 200 ? query.data.data : undefined

  // The manifest lands when the run ends; the ladder only notices on a refetch.
  const wasLive = useRef(false)
  const live = isLive(run)
  useEffect(() => {
    if (wasLive.current && !live)
      void queryClient.invalidateQueries({ queryKey: getListSimulationsQueryKey(experimentId) })
    wasLive.current = live
  }, [live, queryClient, experimentId])

  const refresh = () => void queryClient.invalidateQueries({ queryKey: getGetSetupQueryKey(experimentId, params) })
  const start = useStartSetup({ mutation: { onSuccess: refresh } })
  const stop = useStopSetup({ mutation: { onSuccess: refresh } })
  const startRun = (options: { tier?: StartSetupRequestTier; gpu?: boolean } = {}) =>
    start.mutate({ experimentId, data: { notebook, ...options } }, { onSuccess: () => setExpertOpen(false) })

  if (query.isPending) return <Skeleton className="h-16 w-full" aria-label="Loading setup run" />
  if (query.isError && !missing) return <ApiErrorAlert error={query.error} onRetry={() => void query.refetch()} />

  const runActions = blockedReason === undefined && (
    <>
      <Button type="button" onClick={() => startRun()} disabled={start.isPending}>
        {start.isPending ? <LoaderCircle className="animate-spin" aria-hidden /> : <Play aria-hidden />}
        {run === undefined ? "Run setup" : "Run setup again"}
      </Button>
      <Button type="button" variant="outline" onClick={() => setExpertOpen(true)}>
        Expert
      </Button>
    </>
  )

  return (
    <div className="space-y-4">
      {run === undefined && <p className="text-sm">Prepares the system with the workflow&apos;s defaults.</p>}

      {live && run !== undefined && (
        <section aria-label="Setup progress" className="space-y-2">
          <p role="status" className="flex items-center gap-2 text-sm">
            <LoaderCircle size={16} className="text-primary animate-spin" aria-hidden />
            {run.state === "starting" ? (run.waiting ? "Waiting for resources" : "Starting setup") : stepLabel(run)}
          </p>
          {run.state === "running" && run.total ? (
            <Progress value={((run.step ?? 0) / run.total) * 100} aria-label="Setup progress" />
          ) : null}
          <p className="text-text-muted text-xs">Edits saved in the notebook during the run are overwritten.</p>
        </section>
      )}

      {run?.state === "failed" && (
        <Alert variant="error">
          <AlertTitle>
            {run.error?.step
              ? `Setup stopped at ${stepLabel(run, run.error.step).replace(/^Step/, "step")}`
              : "Setup failed"}
          </AlertTitle>
          <AlertDescription>
            <p>{run.error?.message}</p>
            {run.error?.solution ? <p>{run.error.solution}</p> : null}
          </AlertDescription>
        </Alert>
      )}
      {run?.state === "stopped" && (
        <p className="text-text-muted text-sm">Setup was stopped at {stepLabel(run).replace(/^Step/, "step")}.</p>
      )}
      {run?.state === "done" && <p className="text-sm">Setup finished: {run.manifests?.join(", ")}.</p>}

      {start.error ? <ApiErrorAlert error={start.error} /> : null}
      {stop.error ? <ApiErrorAlert error={stop.error} /> : null}

      <div className="flex flex-wrap items-center gap-2">
        {live ? (
          <Button
            type="button"
            variant="outline"
            className="border-error text-error hover:bg-error/10 hover:text-error"
            onClick={() => stop.mutate({ experimentId, params })}
            disabled={stop.isPending}
          >
            <Square fill="currentColor" aria-hidden />
            Stop
          </Button>
        ) : (
          runActions
        )}
        <Button type="button" variant="link" onClick={onOpenNotebook}>
          {run?.state === "failed" || run?.state === "stopped"
            ? "Fix in notebook"
            : live || run?.state === "done"
              ? "View notebook"
              : "Edit in notebook"}
        </Button>
      </div>
      {!live && blockedReason !== undefined && <p className="text-text-muted text-sm">{blockedReason}</p>}

      <SetupExpertDialog
        open={expertOpen}
        onOpenChange={setExpertOpen}
        pending={start.isPending}
        onRun={(tier, gpu) => startRun({ tier, gpu })}
        error={start.error ?? undefined}
      />
    </div>
  )
}

type SetupExpertDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  pending: boolean
  onRun: (tier: StartSetupRequestTier | undefined, gpu: boolean) => void
  error: unknown
}

/** Setup resources stay behind Expert so the default run never over-asks the quota. */
function SetupExpertDialog({ open, onOpenChange, pending, onRun, error }: SetupExpertDialogProps) {
  const config = useGetNotebookConfig({ query: { retry: false } })
  const tiers = config.data?.status === 200 ? config.data.data.tiers : []
  const defaultTier = config.data?.status === 200 ? config.data.data.defaultTier : undefined
  const [tier, setTier] = useState<StartSetupRequestTier | "">("")
  const [gpu, setGpu] = useState(false)
  const effectiveTier = tier || defaultTier

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Expert setup</DialogTitle>
          <DialogDescription>Run setup with a larger size or a GPU.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {tiers.length > 0 && (
            <div className="space-y-2">
              <Label htmlFor="setup-size">Size</Label>
              <Select value={effectiveTier} onValueChange={(value) => setTier(value as StartSetupRequestTier)}>
                <SelectTrigger id="setup-size" className="w-full">
                  <SelectValue placeholder="Size" />
                </SelectTrigger>
                <SelectContent>
                  {tiers.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.cpuLimit} CPU / {option.memoryLimit} memory
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="flex items-center gap-2">
            <Checkbox id="setup-gpu" checked={gpu} onCheckedChange={(checked) => setGpu(checked === true)} />
            <Label htmlFor="setup-gpu" className="font-normal">
              GPU
            </Label>
          </div>
          {error !== undefined ? <ApiErrorAlert error={error} /> : null}
        </div>
        <DialogFooter>
          <Button type="button" onClick={() => onRun(effectiveTier || undefined, gpu)} disabled={pending}>
            {pending ? <LoaderCircle className="animate-spin" aria-hidden /> : <Play aria-hidden />}
            Run setup
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
