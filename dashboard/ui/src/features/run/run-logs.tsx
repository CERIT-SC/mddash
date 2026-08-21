import { useEffect, useMemo, useRef, useState } from "react"

import { Engine, type SimulationJobLogLines } from "@/api/generated/models"
import {
  Badge,
  Button,
  Checkbox,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Label,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@e-infra/design-system"
import { ChevronDown, Copy, Download } from "lucide-react"
import { toast } from "sonner"

import { countNewlines, toLogHtml } from "./log-text"
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

  const html = useMemo(() => (hasText ? toLogHtml(text) : ""), [hasText, text])
  const paneRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const pane = paneRef.current
    // scrollTop assignment instead of scrollTo — Element.scrollTo is missing in jsdom.
    if (follow && pane) pane.scrollTop = pane.scrollHeight
  }, [html, follow, tab])

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
                  html={html}
                  pending={log.pending && text === undefined}
                  failed={log.failed}
                  label={activeLabel}
                  paneRef={paneRef}
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

type LogPaneProps = {
  html: string
  pending: boolean
  failed: boolean
  label: string
  paneRef: React.RefObject<HTMLDivElement | null>
}

function LogPane({ html, pending, failed, label, paneRef }: LogPaneProps) {
  if (pending) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    )
  }
  if (failed) {
    return <p className="text-text-muted text-sm">The log could not be loaded.</p>
  }
  if (html === "") {
    return <p className="text-text-muted text-sm">{label} is empty.</p>
  }
  return (
    // ansi-to-html escapes XML/HTML entities before converting color codes, so this is safe
    <div
      ref={paneRef}
      className="bg-surface text-text max-h-96 overflow-auto rounded-md p-3 font-mono text-xs break-all whitespace-pre-wrap"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}
