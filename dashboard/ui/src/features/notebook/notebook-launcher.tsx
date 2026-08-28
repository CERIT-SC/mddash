import { useEffect, useState } from "react"

import { toApiError } from "@/api/errors"
import { useGetNotebookConfig, useStartNotebook } from "@/api/generated/client"
import type { Notebook, StartNotebookRequestTier } from "@/api/generated/models"
import {
  Button,
  Checkbox,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@e-infra/design-system"
import { Play } from "lucide-react"
import { toast } from "sonner"

import { NotebookControls } from "./notebook-controls"
import { isNotebookQuotaError, useNotebookInvalidation, useNotebookQuota } from "./notebook-hooks"
import { NotebookQuotaDialog, type PendingNotebookStart } from "./notebook-quota-dialog"

function formatCpu(cpu: string): string {
  const cores = cpu.endsWith("m") ? parseInt(cpu) / 1000 : parseFloat(cpu)
  return `${cores} cores`
}

function formatMemory(memory: string): string {
  if (memory.endsWith("Gi")) return `${parseFloat(memory)} GB`
  if (memory.endsWith("Mi")) return `${(parseFloat(memory) / 1024).toFixed(1)} GB`
  return memory
}

type NotebookLauncherProps = {
  experimentId: string
  /** Undefined while the notebook query is in flight. */
  notebook: Notebook | undefined
  /** Serving probe result for a RUNNING notebook. */
  ready: boolean
  probeFailures: number
  /** Deep link into the notebook (role-picked file when possible). */
  openHref: string
}

export function NotebookLauncher({ experimentId, notebook, ready, probeFailures, openHref }: NotebookLauncherProps) {
  const config = useGetNotebookConfig({ query: { retry: false } })
  const [tier, setTier] = useState<StartNotebookRequestTier | "">("")
  const [gpu, setGpu] = useState(false)

  const tiers = config.data?.status === 200 ? config.data.data.tiers : []
  const defaultTier = config.data?.status === 200 ? config.data.data.defaultTier : undefined
  // Adopt the server default once the config lands.
  useEffect(() => {
    if (defaultTier !== undefined) setTier((current) => current || defaultTier)
  }, [defaultTier])

  const invalidate = useNotebookInvalidation(experimentId)
  const quota = useNotebookQuota()
  const [quotaOpen, setQuotaOpen] = useState(false)
  const [pendingStart, setPendingStart] = useState<PendingNotebookStart | null>(null)

  const start = useStartNotebook({
    mutation: {
      onSuccess: invalidate,
      onError: (error) => {
        if (isNotebookQuotaError(error)) setQuotaOpen(true)
        else toast.error(toApiError(error).message)
      },
    },
  })

  function attemptStart() {
    const request: PendingNotebookStart = { experimentId, data: { tier: tier || undefined, gpu } }
    setPendingStart(request)
    if (quota.full) setQuotaOpen(true)
    else start.mutate(request)
  }

  const status = notebook?.status

  if (notebook !== undefined && status !== "DOWN" && status !== "TERMINATED" && status !== "ERROR") {
    return (
      <div aria-label="Notebook launcher" className="border-border bg-surface w-fit max-w-full rounded-lg border">
        <NotebookControls
          experimentId={experimentId}
          notebook={notebook}
          ready={ready}
          probeFailures={probeFailures}
          openHref={openHref}
        />
      </div>
    )
  }

  return (
    <>
      <div
        aria-label="Notebook launcher"
        className="border-border bg-surface flex w-fit max-w-full flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border px-3 py-2"
      >
        <span className="flex items-center gap-2 text-sm font-medium">
          <span className="bg-text-muted/40 h-2 w-2 rounded-full" aria-hidden="true" />
          Notebook
        </span>
        {tiers.length > 0 && (
          <Select value={tier} onValueChange={(value) => setTier(value as StartNotebookRequestTier)}>
            <SelectTrigger aria-label="Notebook size" className="w-auto min-w-40">
              <SelectValue placeholder="Size" />
            </SelectTrigger>
            <SelectContent>
              {tiers.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {formatCpu(option.cpuLimit)} / {formatMemory(option.memoryLimit)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <div className="flex items-center gap-2">
          <Checkbox
            id={`gpu-${experimentId}`}
            checked={gpu}
            onCheckedChange={(checked) => setGpu(checked === true)}
            aria-label="GPU"
          />
          <Label htmlFor={`gpu-${experimentId}`} className="text-sm font-normal">
            GPU
          </Label>
        </div>
        <Button size="sm" onClick={attemptStart} disabled={start.isPending || (tiers.length > 0 && tier === "")}>
          <Play aria-hidden="true" />
          {start.isPending ? "Starting…" : "Start notebook"}
        </Button>
      </div>
      <NotebookQuotaDialog open={quotaOpen} onOpenChange={setQuotaOpen} pendingStart={pendingStart} />
    </>
  )
}
