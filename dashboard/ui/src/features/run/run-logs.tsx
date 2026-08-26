import { useEffect, useMemo, useState } from "react"

import { Engine, type SimulationJobLogLines } from "@/api/generated/models"
import { countNewlines } from "@/shared/log-text"
import { LogPane } from "@/shared/ui/log-pane"
import {
  Badge,
  Button,
  Checkbox,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Label,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@e-infra/design-system"
import { ChevronDown, Copy, Download } from "lucide-react"
import { toast } from "sonner"

import { engineLogType, LOG_TAIL, useSimulationJobLog } from "./use-simulation-job"

type StreamType = keyof SimulationJobLogLines

type Stream = { type: StreamType; label: string }

function streams(engine: Engine): Stream[] {
  return [
    { type: engineLogType(engine), label: engine === Engine.AMBER ? "Amber log" : "Gromacs log" },
    { type: "stdout", label: "Standard output" },
    { type: "stderr", label: "Standard error" },
  ]
}

type RunLogsProps = {
  experimentId: string
  simulationPath: string
  engine: Engine
  /** Payload line counts — sizes the badges without fetching any stream. */
  logLines: SimulationJobLogLines | undefined
  /** Poll the open stream while the job is alive. */
  live: boolean
  /** Auto-open on the engine error stream when the job failed. */
  failed: boolean
  pollMs: number
}

/**
 * Job run logs: one collapsible block, engine/stdout/stderr tabs. Counts come
 * from the job payload; only the visible stream is fetched (and polled).
 */
export function RunLogs({ experimentId, simulationPath, engine, logLines, live, failed, pollMs }: RunLogsProps) {
  const engineType = engineLogType(engine)
  const allStreams = useMemo(() => streams(engine), [engine])
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<StreamType>(engineType)
  const [follow, setFollow] = useState(true)

  // Failure pulls the error stream into view once; later closes stay manual.
  useEffect(() => {
    if (failed) {
      setOpen(true)
      setTab("stderr")
    }
  }, [failed])

  // Only the visible stream is fetched.
  const log = useSimulationJobLog(experimentId, simulationPath, engine, tab, { enabled: open, live, pollMs })

  const countFor = (type: StreamType) => logLines?.[type] ?? null
  const total = allStreams.reduce((sum, stream) => sum + (countFor(stream.type) ?? 0), 0)
  const activeLabel = allStreams.find((stream) => stream.type === tab)?.label ?? tab
  const text = log.text
  const hasText = text !== undefined && text.trim() !== ""

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text ?? "")
      toast.success("Log copied to the clipboard")
    } catch {
      toast.error("Could not copy the log")
    }
  }

  // e.g. production/md.simulation.json → production/md-gmx.log
  const download = () => {
    const base =
      simulationPath
        .split("/")
        .pop()
        ?.replace(/\.simulation\.json$/, "") ?? "run"
    const url = URL.createObjectURL(new Blob([text ?? ""], { type: "text/plain" }))
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = `${simulationPath.includes("/") ? `${simulationPath.split("/").slice(0, -1).join("-")}-` : ""}${base}-${tab}.log`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const tabCount = countFor(tab)
  const fetchedCount = hasText ? countNewlines(text) : 0

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="flex items-center justify-between">
        <CollapsibleTrigger className="group inline-flex items-center gap-2">
          <ChevronDown className="h-4 w-4 transition-transform group-data-[state=closed]:-rotate-90" aria-hidden />
          <span className="text-lg font-semibold">Logs</span>
          {total > 0 && <Badge variant="secondary">{total.toLocaleString("en-US")}</Badge>}
        </CollapsibleTrigger>
      </div>

      <CollapsibleContent className="space-y-2 pt-3">
        <Tabs value={tab} onValueChange={(next) => setTab(next as StreamType)}>
          {/* Stream actions sit on the selector row: they act on the active tab only. */}
          <div className="flex items-center justify-between gap-2">
            <TabsList aria-label="Log stream">
              {allStreams.map((stream) => {
                const count = countFor(stream.type)
                return (
                  <TabsTrigger key={stream.type} value={stream.type}>
                    {stream.label}
                    {count !== null && count > 0 ? (
                      <Badge variant="secondary" className="ml-1">
                        {count.toLocaleString("en-US")}
                      </Badge>
                    ) : (
                      <span className="text-text-muted ml-1">empty</span>
                    )}
                  </TabsTrigger>
                )
              })}
            </TabsList>
            <div className="flex items-center gap-1">
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`Copy ${activeLabel}`}
                title={`Copy ${activeLabel}`}
                onClick={() => void copy()}
                disabled={!hasText}
              >
                <Copy aria-hidden />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`Download ${activeLabel}`}
                title={`Download ${activeLabel}`}
                onClick={download}
                disabled={!hasText}
              >
                <Download aria-hidden />
              </Button>
            </div>
          </div>
          {allStreams.map((stream) => (
            <TabsContent key={stream.type} value={stream.type} className="pt-2">
              {tab === stream.type && (
                <LogPane
                  logs={text}
                  isLoading={log.pending && text === undefined}
                  errorText={log.failed ? "The log could not be loaded." : undefined}
                  emptyText={`${activeLabel} is empty.`}
                  follow={follow}
                />
              )}
            </TabsContent>
          ))}
        </Tabs>

        {/* The payload count often runs one poll ahead of the refetch — the note
            exists only for a genuinely capped window, never for that transient lag. */}
        {tabCount !== null && fetchedCount >= LOG_TAIL && tabCount > fetchedCount && (
          <p className="text-text-muted text-xs">
            Showing the last {fetchedCount.toLocaleString("en-US")} of {tabCount.toLocaleString("en-US")} lines
          </p>
        )}

        <div className="flex items-center gap-2">
          <Checkbox id="run-logs-follow" checked={follow} onCheckedChange={(checked) => setFollow(checked === true)} />
          <Label htmlFor="run-logs-follow">Follow output</Label>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}
