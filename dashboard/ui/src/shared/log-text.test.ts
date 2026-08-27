import { describe, expect, it } from "vitest"

import { countNewlines, processTerminalOutput, toLogHtml, toLogLinesHtml } from "./log-text"

const ESC = "\x1b"

describe("toLogLinesHtml", () => {
  it("splits plain text into one HTML string per line", () => {
    expect(toLogLinesHtml("alpha\nbeta\ngamma")).toEqual(["alpha", "beta", "gamma"])
  })

  it("keeps blank lines as empty strings", () => {
    expect(toLogLinesHtml("a\n\nb")).toEqual(["a", "", "b"])
  })

  it("closes a span opened on an earlier line and reopens it on the next", () => {
    const lines = toLogLinesHtml(`${ESC}[31mred\nstill red${ESC}[0m\ndone`)
    expect(lines).toHaveLength(3)
    expect(lines[0]).toMatch(/^<span[^>]*>red<\/span>$/)
    expect(lines[1]).toMatch(/^<span[^>]*>still red<\/span>$/)
    expect(lines[2]).toBe("done")
    // Every line is independently well-formed.
    for (const line of lines) {
      const opens = line.match(/<span/g)?.length ?? 0
      const closes = line.match(/<\/span>/g)?.length ?? 0
      expect(opens).toBe(closes)
    }
  })

  it("does not wrap lines after the color resets", () => {
    const lines = toLogLinesHtml(`${ESC}[33mwarning${ESC}[0m\nplain`)
    expect(lines[1]).toBe("plain")
  })

  it("still escapes HTML entities and collapses progress lines", () => {
    expect(toLogLinesHtml("<b>\n10%\r20%")).toEqual(["&lt;b&gt;", "20%"])
  })
})

describe("processTerminalOutput", () => {
  it("leaves plain lines untouched", () => {
    expect(processTerminalOutput("alpha\nbeta")).toBe("alpha\nbeta")
  })

  it("collapses carriage-return overwrites (progress lines keep only the last write)", () => {
    expect(processTerminalOutput("10%\r20%\r30%")).toBe("30%")
    expect(processTerminalOutput("step 100\rstep 200")).toBe("step 200")
  })

  it("tracks the cursor across ANSI codes without leaking hidden text", () => {
    expect(processTerminalOutput(`${ESC}[33mab${ESC}[0m\rcd`)).toBe(`${ESC}[0mcd`)
  })

  it("overwrites in place without trimming the old tail", () => {
    expect(processTerminalOutput("abcdef\rxy")).toBe("xycdef")
  })
})

describe("countNewlines", () => {
  it("counts only terminated lines, matching the job payload's counts", () => {
    expect(countNewlines("a\nb\nc\n")).toBe(3)
    expect(countNewlines("a\nb\nc")).toBe(2)
    expect(countNewlines("")).toBe(0)
  })
})

describe("toLogHtml", () => {
  it("escapes HTML entities", () => {
    expect(toLogHtml("<b>&\"'")).not.toContain("<b>")
    expect(toLogHtml("<b>&\"'")).toContain("&lt;b&gt;")
  })

  it("converts ANSI colors to styled spans", () => {
    const html = toLogHtml(`${ESC}[33mwarning${ESC}[0m`)
    expect(html).toContain("warning")
    expect(html).toMatch(/color|background/)
  })

  it("collapses progress lines before conversion", () => {
    expect(toLogHtml("10%\r20%")).toBe("20%")
  })
})
