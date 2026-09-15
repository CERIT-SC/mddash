import { describe, expect, it } from "vitest"

import { parsePositiveInt } from "./parse"

describe("parsePositiveInt", () => {
  it("parses plain positive integers", () => {
    expect(parsePositiveInt("50000")).toBe(50000)
    expect(parsePositiveInt("1")).toBe(1)
    expect(parsePositiveInt(" 25000 ")).toBe(25000)
  })

  it("rejects inputs parseInt would silently prefix", () => {
    expect(parsePositiveInt("1e5")).toBeNull()
    expect(parsePositiveInt("5.9")).toBeNull()
    expect(parsePositiveInt("100abc")).toBeNull()
  })

  it("rejects empty, zero, negative, and non-numeric input", () => {
    expect(parsePositiveInt("")).toBeNull()
    expect(parsePositiveInt("   ")).toBeNull()
    expect(parsePositiveInt("0")).toBeNull()
    expect(parsePositiveInt("-5")).toBeNull()
    expect(parsePositiveInt("abc")).toBeNull()
  })
})
