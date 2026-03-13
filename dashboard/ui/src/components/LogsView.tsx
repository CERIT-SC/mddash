import { useEffect, useMemo, useRef } from "react"

import AnsiToHtml from "ansi-to-html"

import { cn } from "@/lib/utils"

/**
 * Simulate terminal \r/\n output with ANSI-awareness.
 * \r resets the cursor to column 0; chars that follow overwrite existing ones.
 * ANSI escape codes are preserved but treated as zero-width for cursor tracking,
 * so color codes don't corrupt column positions.
 */
function processTerminalOutput(text: string): string {
  function processLine(raw: string): string {
    if (!raw.includes("\r")) return raw

    // Each cell holds one visible character and any ANSI codes that precede it.
    const cells: { ch: string; ansi: string }[] = []
    let col = 0
    let pendingAnsi = ""
    let i = 0

    while (i < raw.length) {
      // Consume an ANSI escape sequence (zero visual width).
      const ansiMatch = raw.slice(i).match(/^\x1b\[[0-9;]*[A-Za-z]/)
      if (ansiMatch) {
        pendingAnsi += ansiMatch[0]
        i += ansiMatch[0].length
        continue
      }

      const ch = raw[i++]

      if (ch === "\r") {
        col = 0
        continue
      }

      const cell = { ch, ansi: pendingAnsi }
      pendingAnsi = ""

      if (col < cells.length) {
        cells[col] = cell
      } else {
        while (cells.length < col) cells.push({ ch: " ", ansi: "" })
        cells.push(cell)
      }
      col++
    }

    return cells.map((c) => c.ansi + c.ch).join("") + pendingAnsi
  }

  return text.split("\n").map(processLine).join("\n")
}

export interface LogsViewProps {
  logs: string
  className?: string
}

export default function LogsView({ logs, className }: LogsViewProps) {
  const html = useMemo(() => {
    if (!logs) return ""
    // Instantiated inside useMemo to avoid module-level CJS interop issues crashing the app
    const converter = new AnsiToHtml({ escapeXML: true })
    return converter.toHtml(processTerminalOutput(logs))
  }, [logs])

  const cls = cn("max-h-96 w-full overflow-auto rounded-md border p-3 font-mono text-sm whitespace-pre-wrap", className)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = containerRef.current
    if (el) el.scrollTo(0, el.scrollHeight)
  }, [html])

  if (html) {
    // ansi-to-html escapes XML/HTML entities before converting color codes, so this is safe
    return <div className={cls} ref={containerRef} dangerouslySetInnerHTML={{ __html: html }} />
  }

  return (
    <div className={cls} ref={containerRef}>
      Loading...
    </div>
  )
}
