import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { chartPalette, useChartPalette } from "./palette"

const LIGHT: Record<string, string> = {
  "--chart-1": "#111111",
  "--chart-2": "#222222",
  "--chart-3": "#333333",
  "--chart-4": "#444444",
  "--chart-5": "#555555",
  "--chart-6": "#666666",
  "--chart-7": "#777777",
}

const DARK: Record<string, string> = { ...LIGHT, "--chart-1": "#0f0f0f" }

let tokens: Record<string, string>

const mockTokens = () =>
  vi.spyOn(window, "getComputedStyle").mockReturnValue({
    getPropertyValue: (token: string) => tokens[token] ?? "",
  } as CSSStyleDeclaration)

beforeEach(() => {
  tokens = { ...LIGHT }
  mockTokens()
})

afterEach(() => {
  vi.restoreAllMocks()
  document.documentElement.classList.remove("dark")
})

describe("chartPalette", () => {
  it("returns undefined when tokens are not painted", () => {
    vi.restoreAllMocks()
    expect(chartPalette()).toBeUndefined()
  })

  it("resolves painted tokens", () => {
    expect(chartPalette()).toEqual(["#111111", "#222222", "#333333", "#444444", "#555555", "#666666", "#777777"])
  })

  it("returns undefined when any token is missing", () => {
    delete tokens["--chart-4"]
    expect(chartPalette()).toBeUndefined()
  })
})

describe("useChartPalette", () => {
  it("resolves the painted palette", () => {
    const { result } = renderHook(() => useChartPalette())
    expect(result.current?.[0]).toBe("#111111")
  })

  it("re-resolves when the theme class toggles", async () => {
    const { result } = renderHook(() => useChartPalette())
    expect(result.current?.[0]).toBe("#111111")

    await act(async () => {
      tokens = { ...DARK }
      document.documentElement.classList.add("dark")
    })

    expect(result.current?.[0]).toBe("#0f0f0f")
  })
})
