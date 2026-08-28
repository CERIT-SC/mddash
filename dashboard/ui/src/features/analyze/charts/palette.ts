import { useSyncExternalStore } from "react"

const CHART_TOKENS = [
  "--chart-1",
  "--chart-2",
  "--chart-3",
  "--chart-4",
  "--chart-5",
  "--chart-6",
  "--chart-7",
] as const

export function chartPalette(): string[] | undefined {
  if (typeof window === "undefined") return undefined
  const styles = getComputedStyle(document.documentElement)
  const palette = CHART_TOKENS.map((token) => styles.getPropertyValue(token).trim())
  return palette.every(Boolean) ? palette : undefined
}

function subscribeToTheme(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] })
  return () => observer.disconnect()
}

const getTheme = (): string => (document.documentElement.classList.contains("dark") ? "dark" : "light")

let cachedTheme: string | null = null
let cachedPalette: string[] | undefined

const getPalette = (): string[] | undefined => {
  const theme = getTheme()
  if (theme !== cachedTheme) {
    cachedTheme = theme
    cachedPalette = chartPalette()
  }
  return cachedPalette
}

export function useChartPalette(): string[] | undefined {
  return useSyncExternalStore(subscribeToTheme, getPalette, () => undefined)
}
