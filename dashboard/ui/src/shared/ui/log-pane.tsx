import { useEffect, useMemo, useRef } from "react"

import { toLogHtml } from "@/shared/log-text"
import { cn } from "@e-infra/design-system"

export type LogPaneProps = {
  /** Raw log text; empty/whitespace renders the empty state. */
  logs?: string
  /** Show the loading state instead of content. */
  isLoading?: boolean
  /** Pin the scroll to the latest output (default true); the run step can turn it off via "Follow output". */
  follow?: boolean
  /** Loading-state text (default "waiting for output..."). */
  loadingText?: string
  /** Empty-log text (default "(no output)"). */
  emptyText?: string
  /** Overrides all other states when set — the log endpoint failed. */
  errorText?: string
  className?: string
}

/**
 * Monospaced, ANSI-colored log pane shared by the run and analyze steps:
 * terminal \r-overwrites collapsed, colors via ansi-to-html, scroll pinned to
 * the latest output unless `follow` is false.
 */
export function LogPane({
  logs,
  isLoading = false,
  follow = true,
  loadingText = "waiting for output...",
  emptyText = "(no output)",
  errorText,
  className,
}: LogPaneProps) {
  const html = useMemo(() => (logs?.trim() ? toLogHtml(logs) : ""), [logs])

  const paneRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = paneRef.current
    // scrollTop assignment instead of scrollTo — Element.scrollTo is missing in jsdom.
    if (follow && el) el.scrollTop = el.scrollHeight
  }, [html, follow])

  const cls = cn(
    "border-border bg-surface text-text max-h-96 w-full overflow-auto rounded-md border p-3 font-mono text-xs break-all whitespace-pre-wrap",
    className
  )

  if (errorText !== undefined) {
    return <div className={cn(cls, "text-text-muted")}>{errorText}</div>
  }
  if (isLoading) {
    return <div className={cn(cls, "text-text-muted animate-pulse select-none")}>{loadingText}</div>
  }
  if (html) {
    // ansi-to-html escapes XML/HTML entities before converting color codes, so this is safe
    return <div ref={paneRef} className={cls} dangerouslySetInnerHTML={{ __html: html }} />
  }
  return <div className={cn(cls, "text-text-muted/70 italic select-none")}>{emptyText}</div>
}
