import AnsiToHtml from "ansi-to-html"

/**
 * Collapse \r overwrites per line (GROMACS progress lines rewrite one line in place);
 * ANSI codes are tracked as zero-width cell prefixes so they survive column-wise rewriting.
 */
export function processTerminalOutput(text: string): string {
  function processLine(raw: string): string {
    if (!raw.includes("\r")) return raw

    const cells: { ch: string; ansi: string }[] = []
    let col = 0
    let pendingAnsi = ""
    let i = 0

    while (i < raw.length) {
      // Consume an ANSI escape sequence (zero visual width).
      // eslint-disable-next-line no-control-regex
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

      if (col < cells.length) cells[col] = cell
      else cells.push(cell)
      col++
    }

    return cells.map((c) => c.ansi + c.ch).join("") + pendingAnsi
  }

  return text.split("\n").map(processLine).join("\n")
}

/** wc -l semantics; must match the server-side `log_lines` count for truncation comparison. */
export function countNewlines(text: string): number {
  let count = 0
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "\n") count++
  }
  return count
}

/** Collapse terminal-overwrite lines, then convert ANSI to escaped HTML. */
export function toLogHtml(text: string): string {
  // Instantiated per call — module-level instantiation hit CJS interop issues in the legacy UI.
  const converter = new AnsiToHtml({ escapeXML: true })
  return converter.toHtml(processTerminalOutput(text))
}

const SPAN_TAG = /<\/?span(?:\s[^>]*)?>/g

/**
 * toLogHtml split per line, each line independently well-formed. ansi-to-html
 * keeps a color span open across \n, so a naive split would leave unclosed
 * spans: spans still open at a line boundary are closed at that line's end and
 * reopened on the next line. Per-line HTML lets the log pane render memoized
 * rows and append live output without re-rendering the whole tail.
 */
export function toLogLinesHtml(text: string): string[] {
  const open: string[] = []
  return toLogHtml(text)
    .split("\n")
    .map((line) => {
      const prefix = open.join("")
      const stack = [...open]
      for (const [tag] of line.matchAll(SPAN_TAG)) {
        if (tag.startsWith("</")) stack.pop()
        else stack.push(tag)
      }
      open.length = 0
      open.push(...stack)
      return prefix + line + "</span>".repeat(stack.length)
    })
}
